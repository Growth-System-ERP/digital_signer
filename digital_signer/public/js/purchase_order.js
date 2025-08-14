frappe.ui.form.on("Purchase Order", {
    refresh: function(frm) {
        if (frm.doc.docstatus == 1) {
            // Check if USB key is configured
            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: "Document Sign Setting",
                    name: "Document Sign Setting"
                },
                callback: function(r) {
                    if (r.message) {
                        const use_usb = r.message.use_usb_key;
                        const password_label = use_usb ? "Enter USB Key PIN" : "Enter PFX Password";
                        const password_help = use_usb ? "Enter the PIN for your USB security key" : "";

                        // Add sign buttons
                        frm.add_custom_button("Sign & Attach PDF", function() {
                            frappe.call({
                                method: "frappe.client.get_list",
                                args: {
                                    doctype: "Print Format",
                                    filters: {
                                        doc_type: frm.doctype,
                                        disabled : 0
                                    },
                                    fields: ["name"]
                                },
                                callback: function(res) {
                                    if (res.message) {
                                        let print_formats = res.message.map(f => f.name);

                                        let d = new frappe.ui.Dialog({
                                            title: use_usb ? 'Sign with USB Security Key' : 'Choose Print Format',
                                            fields: [
                                                {
                                                    label: 'Select Print Format',
                                                    fieldname: 'print_format',
                                                    fieldtype: 'Select',
                                                    options: print_formats,
                                                    reqd: 1
                                                },
                                                {
                                                    fieldname: 'password',
                                                    fieldtype: 'Password',
                                                    label: password_label,
                                                    description: password_help,
                                                    reqd: 1
                                                },
                                                {
                                                    fieldname: 'multiple_page_sign',
                                                    fieldtype: 'Check',
                                                    label: 'Sign All Pages (Multiple Pages)',
                                                                     depends_on: 'eval: !doc.page_range_enable',
                                                                     hidden: use_usb  // Simplify for USB key usage
                                                },
                                                {
                                                    fieldname: 'page_range_enable',
                                                    fieldtype: 'Check',
                                                    label: 'Sign Specific Page Range',
                                                    depends_on: 'eval: !doc.multiple_page_sign',
                                                    hidden: use_usb
                                                },
                                                {
                                                    fieldname: 'page_range',
                                                    fieldtype: 'Data',
                                                    label: 'Page Range (e.g., 1,3-5)',
                                                                     depends_on: 'eval: doc.page_range_enable',
                                                                     hidden: use_usb
                                                }
                                            ],
                                            primary_action_label: 'Sign & Attach',
                                            primary_action(values) {
                                                d.hide();

                                                // Show progress for USB key operations
                                                if (use_usb) {
                                                    frappe.show_progress('Signing with USB Key', 0, 100, 'Please wait...');
                                                }

                                                frappe.call({
                                                    method: "digital_signer.api.sign_sales_invoice_pdf",
                                                    args: {
                                                        doctype: frm.doctype,
                                                        sales_invoice_name: frm.doc.name,
                                                        print_format_name: values.print_format,
                                                        entered_password: values.password,
                                                        multiple_page: values.multiple_page_sign ? 1 : 0,
                                                        page_range: values.page_range || ""
                                                    },
                                                    callback: function(r) {
                                                        frappe.hide_progress();
                                                        if (!r.exc) {
                                                            frappe.msgprint({
                                                                title: __('Success'),
                                                                            indicator: 'green',
                                                                            message: use_usb ?
                                                                            __('PDF signed with USB security key and attached successfully!') :
                                                                            __('Signed PDF attached successfully!')
                                                            });
                                                            frm.reload_doc();
                                                        }
                                                    },
                                                    error: function(r) {
                                                        frappe.hide_progress();
                                                        if (use_usb && r.message && r.message.includes("PIN")) {
                                                            frappe.msgprint({
                                                                title: __('Authentication Failed'),
                                                                            indicator: 'red',
                                                                            message: __('Invalid PIN. Please check your USB key PIN and try again. Warning: Multiple failed attempts may lock your USB key.')
                                                            });
                                                        }
                                                    }
                                                });
                                            }
                                        });

                                        d.show();
                                    }
                                }
                            });
                        }, "Sign");

                        frm.add_custom_button("Sign with Preview PDF", function() {
                            frappe.call({
                                method: "frappe.client.get_list",
                                args: {
                                    doctype: "Print Format",
                                    filters: {
                                        doc_type: frm.doctype,
                                        disabled: 0
                                    },
                                    fields: ["name"]
                                },
                                callback: function(res) {
                                    if (res.message) {
                                        let print_formats = res.message.map(f => f.name);
                                        let signature_data = [];

                                        const dialog = new frappe.ui.Dialog({
                                            title: use_usb ? 'Sign PDF with USB Security Key' : 'Sign PDF',
                                            fields: [
                                                {
                                                    label: 'Select Print Format',
                                                    fieldname: 'print_format',
                                                    fieldtype: 'Select',
                                                    options: print_formats,
                                                    reqd: 1
                                                },
                                                {
                                                    label: password_label,
                                                    fieldname: 'password',
                                                    fieldtype: 'Password',
                                                    description: password_help,
                                                    reqd: 1
                                                },
                                                {
                                                    label: 'Preview & Select Signature Locations',
                                                    fieldname: 'preview_btn',
                                                    fieldtype: 'Button'
                                                }
                                            ],
                                            primary_action_label: 'Sign & Attach',
                                            primary_action(values) {
                                                if (signature_data.length === 0) {
                                                    frappe.msgprint("Please select at least one signature location.");
                                                    return;
                                                }
                                                dialog.hide();

                                                if (use_usb) {
                                                    frappe.show_progress('Signing with USB Key', 0, 100, 'Communicating with USB security key...');
                                                }

                                                frappe.call({
                                                    method: "digital_signer.preview_api.sign_sales_invoice_pdf",
                                                    args: {
                                                        doctype: frm.doctype,
                                                        sales_invoice_name: frm.doc.name,
                                                        print_format_name: values.print_format,
                                                        entered_password: values.password,
                                                        coordinates_json: JSON.stringify(signature_data)
                                                    },
                                                    callback: function(r) {
                                                        frappe.hide_progress();
                                                        if (!r.exc) {
                                                            frappe.msgprint({
                                                                title: __('Success'),
                                                                            indicator: 'green',
                                                                            message: use_usb ?
                                                                            __('PDF signed with USB security key and attached successfully!') :
                                                                            __('Signed PDF attached successfully!')
                                                            });
                                                            frm.reload_doc();
                                                        }
                                                    },
                                                    error: function(r) {
                                                        frappe.hide_progress();
                                                        if (use_usb) {
                                                            frappe.msgprint({
                                                                title: __('USB Key Error'),
                                                                            indicator: 'red',
                                                                            message: __('Failed to sign with USB key. Please ensure the device is connected and the PIN is correct.')
                                                            });
                                                        }
                                                    }
                                                });
                                            }
                                        });

                                        // Preview button click
                                        dialog.fields_dict.preview_btn.df.click = function() {
                                            const print_format = dialog.get_value('print_format');
                                            if (!print_format) {
                                                frappe.msgprint("Please select a print format.");
                                                return;
                                            }

                                            const pdf_url = `/api/method/frappe.utils.print_format.download_pdf?doctype=${frm.doctype}&name=${frm.doc.name}&format=${print_format}&no_letterhead=0`;
                                            const previewWindow = window.open("", "_blank");

                                            previewWindow.document.write(`
                                            <html>
                                            <head>
                                            <title>Select Signature Locations</title>
                                            <style>
                                            body { font-family: Arial; margin: 0; padding: 10px; }
                                            canvas { display: block; margin-bottom: 20px; border: 1px solid #ccc; cursor: crosshair; }
                                            h3 { margin-bottom: 10px; }
                                            .info-box {
                                                background: #f0f0f0;
                                                padding: 10px;
                                                margin-bottom: 10px;
                                                border-radius: 5px;
                                            }
                                            </style>
                                            </head>
                                            <body>
                                            ${use_usb ? '<div class="info-box">Using USB Security Key for signing. PIN will be required when signing.</div>' : ''}
                                            <h3>Click on the location where you want the signature (multiple locations allowed)</h3>
                                            <div id="pdf-container"></div>

                                            <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.13.216/pdf.min.js"></script>
                                            <script>
                                            const url = "${pdf_url}";
                                            const container = document.getElementById("pdf-container");
                                            const scale = 1.5;

                                            pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.13.216/pdf.worker.min.js";

                                            pdfjsLib.getDocument(url).promise.then(pdf => {
                                                for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
                                                    pdf.getPage(pageNum).then(page => {
                                                        const viewport = page.getViewport({ scale: scale });
                                                        const canvas = document.createElement("canvas");
                                                        canvas.width = viewport.width;
                                                        canvas.height = viewport.height;
                                                        canvas.dataset.page = pageNum;
                                                        const context = canvas.getContext("2d");

                                                        page.render({ canvasContext: context, viewport: viewport });

                                                        canvas.addEventListener("click", function(event) {
                                                            const rect = canvas.getBoundingClientRect();
                                                            const clickX = event.clientX - rect.left;
                                                            const clickY = event.clientY - rect.top;
                                                            const pdfX = clickX / scale;
                                                            const pdfY = (rect.height - clickY) / scale;

                                                            window.opener.postMessage({
                                                                type: "signature_location",
                                                                x: Math.round(pdfX),
                                                                                      y: Math.round(pdfY),
                                                                                      page: parseInt(canvas.dataset.page)
                                                            }, "*");

                                                            alert("Signature location captured at X: " + Math.round(pdfX) + ", Y: " + Math.round(pdfY) + ". You can select more or close this window.");
                                                        });

                                                        container.appendChild(canvas);
                                                    });
                                                }
                                            });
                                            </script>
                                            </body>
                                            </html>
                                            `);
                                            previewWindow.document.close();
                                        };

                                        // Listen for messages from popup window
                                        window.addEventListener("message", function(event) {
                                            if (event.data && event.data.type === "signature_location") {
                                                signature_data.push(event.data);
                                                frappe.msgprint(`Signature location added: Page ${event.data.page}, X: ${event.data.x}, Y: ${event.data.y}`);
                                            }
                                        });

                                        dialog.show();
                                    }
                                }
                            });
                        }, "Sign");
                    }
                }
            });
        }
    }
});
