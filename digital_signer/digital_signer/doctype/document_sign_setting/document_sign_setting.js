// Copyright (c) 2025, IBSL and contributors
// For license information, please see license.txt

frappe.ui.form.on('Document Sign Setting', {
	refresh: function(frm) {
		// Add custom button to test USB connection
		if (frm.doc.use_usb_key) {
			frm.add_custom_button(__('Test USB Connection'), function() {
				frappe.call({
					method: 'digital_signer.preview_api.test_usb_key_connection',
					callback: function(r) {
						if (r.message) {
							if (r.message.status === 'success') {
								let slot_info = '';
								if (r.message.slots) {
									slot_info = '<br><br><b>Available Slots:</b><ul>';
									r.message.slots.forEach(slot => {
										slot_info += `<li>Slot ${slot.slot_id}: ${slot.description} (${slot.manufacturer})</li>`;
									});
									slot_info += '</ul>';
								}
								frappe.msgprint({
									title: __('USB Key Connected'),
												indicator: 'green',
												message: r.message.message + slot_info
								});
							} else if (r.message.status === 'warning') {
								frappe.msgprint({
									title: __('No USB Key Found'),
												indicator: 'orange',
												message: r.message.message + '<br><br>Please ensure your USB security key is properly connected.'
								});
							} else {
								frappe.msgprint({
									title: __('Connection Error'),
												indicator: 'red',
												message: r.message.message
								});
							}
						}
					}
				});
			}, __('USB Key'));
		}
	},

	use_usb_key: function(frm) {
		// Clear file fields when switching to USB key
		if (frm.doc.use_usb_key) {
			frm.set_value('pfx_file_use', 0);
			frm.set_value('pfx_file', '');
			frm.set_value('certificate', '');
			frm.set_value('private_key', '');
		}
	},

	pfx_file_use: function(frm) {
		// Clear certificate/key fields when switching to PFX
		if (frm.doc.pfx_file_use && !frm.doc.use_usb_key) {
			frm.set_value('certificate', '');
			frm.set_value('private_key', '');
		}
	}
});
