# Add this import section at the top of api.py
try:
    from pyhanko.sign.signers.pdf_cms import PKCS11Signer
    from pkcs11 import lib as pkcs11_lib
    PKCS11_AVAILABLE = True
except ImportError:
    PKCS11_AVAILABLE = False

# Add this helper function to api.py
def get_signer_from_settings(digi, entered_password):
    """
    Get signer based on Document Sign Settings configuration
    Supports USB Key, PFX file, or Certificate+Key
    """
    if digi.use_usb_key:
        # USB Security Key signing
        if not PKCS11_AVAILABLE:
            frappe.throw("PKCS11 support not installed. Please install python-pkcs11 package.")

        pkcs11_library_path = digi.pkcs11_library_path
        if not pkcs11_library_path:
            # Try common default paths
            common_paths = [
                "/usr/lib/opensc-pkcs11.so",
                "/usr/lib/x86_64-linux-gnu/opensc-pkcs11.so",
                "/usr/local/lib/opensc-pkcs11.so",
                "C:\\Windows\\System32\\eTPKCS11.dll",
                "C:\\Windows\\System32\\eps2003csp11.dll",
            ]
            for path in common_paths:
                if os.path.exists(path):
                    pkcs11_library_path = path
                    break

            if not pkcs11_library_path:
                frappe.throw("PKCS11 library not found. Please specify the library path in settings.")

        try:
            slot_no = int(digi.usb_key_slot or 0)
            signer = PKCS11Signer(
                pkcs11_library_path,
                slot_no=slot_no,
                user_pin=entered_password,
                cert_label=digi.usb_cert_label
            )
            return signer
        except Exception as e:
            frappe.throw(f"USB key authentication failed: {str(e)}")

    elif digi.pfx_file_use:
        # PFX file signing
        pfx = digi.pfx_file
        if not pfx:
            frappe.throw("PFX not uploaded in Document Sign Setting.")
        pfx_file_path = frappe.get_site_path(digi.pfx_file.lstrip("/"))

        if not os.path.exists(pfx_file_path):
            frappe.throw(f"PFX file not found: {pfx_file_path}")

        try:
            return signers.SimpleSigner.load_pkcs12(
                pfx_file_path,
                passphrase=entered_password.encode()
            )
        except Exception:
            frappe.throw("Incorrect password for the DSC file.")

    else:
        # Certificate + Private Key signing
        cert = digi.certificate
        pvt = digi.private_key

        if not cert or not pvt:
            frappe.throw("Private Key or Certificate not uploaded in Document Sign Setting.")

        cert_path = frappe.get_site_path(cert.lstrip("/"))
        key_path = frappe.get_site_path(pvt.lstrip("/"))

        if not os.path.exists(cert_path) or not os.path.exists(key_path):
            frappe.throw("Certificate or Private Key file not found on server.")

        return signers.SimpleSigner.load(key_path, cert_path)

# Then in your existing sign_sales_invoice_pdf function, replace the signer loading logic with:
# Instead of the current if/else blocks for loading signer, use:
digi = frappe.get_doc("Document Sign Setting")

# Validate password/PIN
if not digi.use_usb_key:
    actual_password = digi.get_password('dsc_password')
    if entered_password != actual_password:
        frappe.throw("Password is wrong.")
# For USB key, PIN is validated by the device

# Get signer
signer = get_signer_from_settings(digi, entered_password)
