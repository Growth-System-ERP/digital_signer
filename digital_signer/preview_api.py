import frappe
import os
from io import BytesIO
import json
from pyhanko.sign import signers
from pyhanko.sign.signers import PdfSigner, PdfSignatureMetadata
from pyhanko.sign.fields import SigFieldSpec, append_signature_field
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.stamp import QRStampStyle
from PyPDF2 import PdfReader
from frappe import ValidationError

# Import PKCS11 support - only if USB key is used
try:
    from pyhanko.sign.signers.pdf_cms import PKCS11Signer
    from pkcs11 import lib as pkcs11_lib
    PKCS11_AVAILABLE = True
except ImportError:
    PKCS11_AVAILABLE = False
    frappe.log_error("PKCS11 support not available. Install python-pkcs11 for USB key support.")

def get_usb_signer(digi, entered_password):
    """
    Get signer object for USB security key using PKCS#11
    """
    if not PKCS11_AVAILABLE:
        frappe.throw("PKCS11 support not installed. Please install python-pkcs11 package.")

    # Get PKCS#11 library path (e.g., /usr/lib/opensc-pkcs11.so for Linux)
    pkcs11_library_path = digi.pkcs11_library_path
    if not pkcs11_library_path:
        # Try common default paths
        common_paths = [
            "/usr/lib/opensc-pkcs11.so",  # Linux with OpenSC
            "/usr/lib/x86_64-linux-gnu/opensc-pkcs11.so",  # Ubuntu/Debian
            "/usr/local/lib/opensc-pkcs11.so",  # Alternative Linux
            "C:\\Windows\\System32\\eTPKCS11.dll",  # Windows eToken
            "C:\\Windows\\System32\\eps2003csp11.dll",  # Windows SafeNet
        ]
        for path in common_paths:
            if os.path.exists(path):
                pkcs11_library_path = path
                break

        if not pkcs11_library_path:
            frappe.throw("PKCS11 library not found. Please specify the library path in settings.")

    # Create PKCS11 signer
    try:
        # Use slot index (usually 0 for first slot)
        slot_no = int(digi.usb_key_slot or 0)

        # Create signer with user PIN
        signer = PKCS11Signer(
            pkcs11_library_path,
            slot_no=slot_no,
            user_pin=entered_password,
            cert_label=digi.usb_cert_label  # Optional: specific certificate label
        )

        return signer
    except Exception as e:
        frappe.log_error(f"USB Key initialization failed: {str(e)}", "USB Key Error")
        frappe.throw(f"Failed to initialize USB security key: {str(e)}")

def get_signer(digi, entered_password):
    """
    Get appropriate signer based on configuration
    Returns a signer object for PFX, cert/key files, or USB key
    """
    if digi.use_usb_key:
        # USB Security Key signing
        return get_usb_signer(digi, entered_password)
    elif digi.pfx_file_use:
        # PFX file signing
        pfx_file_path = frappe.get_site_path(digi.pfx_file.lstrip("/"))
        if not os.path.exists(pfx_file_path):
            frappe.throw(f"PFX file not found: {pfx_file_path}")
        return signers.SimpleSigner.load_pkcs12(
            pfx_file_path,
            signature_mechanism=None,
            passphrase=entered_password.encode()
        )
    else:
        # Certificate + Private Key signing
        cert_path = frappe.get_site_path(digi.certificate.lstrip("/"))
        key_path = frappe.get_site_path(digi.private_key.lstrip("/"))
        if not os.path.exists(cert_path) or not os.path.exists(key_path):
            frappe.throw("Certificate or Private Key file not found on server.")
        return signers.SimpleSigner.load(key_path, cert_path)

@frappe.whitelist()
def sign_sales_invoice_pdfs(doctype, sales_invoice_name, print_format_name=None, entered_password=None, x=0, y=0, page_range=None):
    try:
        # Get Sales Invoice Doc
        sales_invoice = frappe.get_doc(doctype, sales_invoice_name)

        # Get PDF content of Sales Invoice
        pdf_content = frappe.get_print(
            doctype,
            sales_invoice_name,
            print_format=print_format_name or "Digital Sign",
            as_pdf=True
        )

        # Get Document Sign Setting doc for DSC details
        digi = frappe.get_doc("Document Sign Setting")

        # Password validation
        if not digi.use_usb_key:
            # For file-based signing, validate against stored password
            actual_password = digi.get_password('dsc_password')
            if entered_password != actual_password:
                frappe.throw("Password is wrong.")
        # For USB key, the PIN is validated by the device itself

        # Get appropriate signer
        signer = get_signer(digi, entered_password)

        # Load PDF and get page count
        input_pdf_io = BytesIO(pdf_content)
        pdf_reader = PdfReader(input_pdf_io)
        num_pages = len(pdf_reader.pages)

        # Validate page number received from frontend (1-based)
        try:
            page_num = int(page_range or 1) - 1  # zero-based
        except Exception:
            page_num = 0

        if page_num < 0 or page_num >= num_pages:
            frappe.throw(f"Page number {page_num + 1} is out of range for the PDF.")

        # Prepare incremental writer
        input_pdf_io.seek(0)
        reader = IncrementalPdfFileWriter(input_pdf_io)

        # Signature box coordinates
        sig_width = 200
        sig_height = 50
        sig_box = (float(x), float(y), float(x) + sig_width, float(y) + sig_height)

        # Append signature field to specified page at clicked location
        sig_field_spec = SigFieldSpec(
            sig_field_name=f"Signature_Page_{page_num + 1}",
            box=sig_box,
            on_page=page_num
        )
        append_signature_field(reader, sig_field_spec)

        # Signature metadata
        signature_meta = PdfSignatureMetadata(
            field_name=sig_field_spec.sig_field_name,
            reason=f"Digitally signed on {doctype}",
            location=digi.sign_address or "India"
        )

        # Setup signer with QR stamp style
        pdf_signer = PdfSigner(
            signature_meta,
            signer=signer,
            stamp_style=QRStampStyle(
                stamp_text="For: %(signer)s\nTime: %(ts)s"
            )
        )

        output = BytesIO()
        pdf_signer.sign_pdf(
            reader,
            output=output,
            appearance_text_params={'url': digi.url}
        )

        # Save signed PDF as private attachment
        output.seek(0)
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": f"{sales_invoice.name}-signed.pdf",
            "attached_to_doctype": doctype,
            "attached_to_name": sales_invoice.name,
            "is_private": 1,
            "content": output.getvalue(),
            "decode": False,
        })
        file_doc.insert(ignore_permissions=True)

        return "success"

    except ValidationError:
        raise
    except Exception as e:
        frappe.log_error(f"Error in sign_sales_invoice_pdf: {str(e)}", f"{doctype} PDF Signing")
        frappe.throw(f"Failed to sign PDF: {str(e)}")

@frappe.whitelist()
def sign_sales_invoice_pdf(doctype, sales_invoice_name, print_format_name=None, entered_password=None, coordinates_json=None):
    try:
        sales_invoice = frappe.get_doc(doctype, sales_invoice_name)

        pdf_content = frappe.get_print(
            doctype,
            sales_invoice_name,
            print_format=print_format_name or "Standard",
            as_pdf=True
        )

        digi = frappe.get_doc("Document Sign Setting")

        # Password/PIN validation
        if not digi.use_usb_key:
            actual_password = digi.get_password('dsc_password')
            if entered_password != actual_password:
                frappe.throw("Password is wrong.")

        # Get appropriate signer
        try:
            signer = get_signer(digi, entered_password)
        except Exception as e:
            if digi.use_usb_key:
                frappe.throw(f"USB key authentication failed. Please check your PIN and ensure the device is connected: {str(e)}")
            else:
                frappe.throw("Incorrect password for the DSC file.")

        coordinates = json.loads(coordinates_json or "[]")
        if not coordinates:
            frappe.throw("No signature coordinates provided.")

        input_pdf_io = BytesIO(pdf_content)
        pdf_reader = PdfReader(input_pdf_io)
        num_pages = len(pdf_reader.pages)

        input_pdf_io.seek(0)
        reader = IncrementalPdfFileWriter(input_pdf_io)
        sig_width = 200
        sig_height = 50

        for i, coord in enumerate(coordinates):
            page = int(coord.get("page", 1)) - 1
            x = float(coord.get("x", 0))
            y = float(coord.get("y", 0))
            if page < 0 or page >= num_pages:
                frappe.throw(f"Page number {page + 1} is out of range.")
            box = (x, y, x + sig_width, y + sig_height)
            field_name = f"Signature_Page_{page+1}_{i+1}"

            sig_spec = SigFieldSpec(sig_field_name=field_name, box=box, on_page=page)
            append_signature_field(reader, sig_spec)

            signature_meta = PdfSignatureMetadata(
                field_name=field_name,
                reason=f"Digitally signed on {doctype}",
                location=digi.sign_address or "India"
            )
            signer_obj = PdfSigner(
                signature_meta,
                signer=signer,
                stamp_style=QRStampStyle(stamp_text="For: %(signer)s\nTime: %(ts)s")
            )

            output = BytesIO()
            signer_obj.sign_pdf(reader, output=output, appearance_text_params={'url': digi.url})
            output.seek(0)
            reader = IncrementalPdfFileWriter(output)

        final_output = output.getvalue()

        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": f"{sales_invoice.name}-signed.pdf",
            "attached_to_doctype": doctype,
            "attached_to_name": sales_invoice.name,
            "is_private": 1,
            "content": final_output,
            "decode": False,
        })
        file_doc.insert(ignore_permissions=True)

        return "success"

    except ValidationError:
        raise
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"{doctype} Digital Sign Error")
        frappe.msgprint("Error log created.")
        if digi.use_usb_key:
            frappe.throw("USB key signing failed. Please ensure the device is connected and the PIN is correct.")
        else:
            frappe.throw("You entered an incorrect password in Document Sign Setting, or the PFX file is invalid. Please check the error log for more details.")

@frappe.whitelist()
def test_usb_key_connection():
    """
    Test if USB security key is connected and accessible
    """
    try:
        if not PKCS11_AVAILABLE:
            return {"status": "error", "message": "PKCS11 support not installed"}

        digi = frappe.get_doc("Document Sign Setting")
        pkcs11_library_path = digi.pkcs11_library_path

        if not pkcs11_library_path:
            return {"status": "error", "message": "PKCS11 library path not configured"}

        # Try to load the library and list slots
        lib = pkcs11_lib(pkcs11_library_path)
        slots = lib.get_slots(token_present=True)

        if not slots:
            return {"status": "warning", "message": "No USB security keys detected"}

        slot_info = []
        for slot in slots:
            info = {
                "slot_id": slot.slot_id,
                "description": slot.get_token().label.strip(),
                "manufacturer": slot.get_token().manufacturer_id.strip()
            }
            slot_info.append(info)

        return {
            "status": "success",
            "message": f"Found {len(slots)} USB security key(s)",
            "slots": slot_info
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
