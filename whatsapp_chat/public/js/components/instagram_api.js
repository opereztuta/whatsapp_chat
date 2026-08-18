const METHOD = "frappe_instagram.api.ui.";

export async function instagram_call(method, args = {}, type = "GET") {
  const response = await frappe.call({
    method: METHOD + method,
    args,
    type,
  });
  return response.message;
}

export function instagram_request_id() {
  if (window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
