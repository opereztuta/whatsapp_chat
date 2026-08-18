export default class InstagramBubble {
  constructor(parent) {
    this.parent = parent;
    this.$bubble = $(document.createElement("div"));
    this.$bubble.attr({
      id: "instagram-bubble",
      title: __("Show Instagram Chats"),
    });
    this.render_state();
  }

  render_state() {
    this.$bubble.html(`
      <div class='p-3 chat-bubble ${this.parent.is_desk ? "d-none" : ""}'>
        <span class='chat-message-icon'>${frappe.utils.icon(
          this.parent.is_open ? "close-alt" : "image",
          "lg"
        )}</span>
        <div>${
          this.parent.is_open
            ? __("Close Instagram Chat")
            : __("Show Instagram Chats")
        }</div>
      </div>
    `);
  }

  render() {
    this.parent.$app_element.append(this.$bubble);
    this.$bubble.on("click", () => this.toggle());
  }

  toggle() {
    this.parent.is_open = !this.parent.is_open;
    this.render_state();
    this.parent.$element.toggle(this.parent.is_open);
    if (this.parent.is_open) this.parent.panel.refresh_conversations();
  }
}
