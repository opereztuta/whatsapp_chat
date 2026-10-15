const METHOD = "frappe_instagram.api.ui.";

export async function instagram_call(method, args = {}, type = "GET") {
  const response = await frappe.call({
    method: METHOD + method,
    args,
    type,
  });
  const result = response.message;
  if (
    type === "POST" &&
    (result?.ok === false || result?.status === "failed")
  ) {
    throw new Error(
      result.error?.message ||
        result.failure_reason ||
        __("Instagram message could not be sent.")
    );
  }
  return result;
}

export function instagram_request_id() {
  if (window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
