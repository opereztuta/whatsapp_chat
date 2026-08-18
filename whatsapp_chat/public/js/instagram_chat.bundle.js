import { get_settings } from "./components/chat_utils";
import InstagramBubble from "./components/instagram_bubble";
import InstagramPanel from "./components/instagram_panel";

frappe.provide("frappe.InstagramChat");

frappe.InstagramChat = class {
  constructor() {
    this.setup();
  }

  async setup() {
    try {
      this.is_desk = "desk" in frappe;
      if (!this.is_desk || frappe.session.user === "Guest") return;
      const settings = await get_settings();
      if (!settings.can_access_instagram) return;
      const config = await frappe.call({
        method: "frappe_instagram.api.ui.bootstrap",
      });
      if (!config.message || !config.message.enabled) return;
      this.is_open = false;
      this.$app_element = $(document.createElement("div")).addClass(
        "instagram-app chat-app"
      );
      this.$element = $(document.createElement("div"))
        .addClass("chat-element instagram-element")
        .attr("id", "instagram-chat-panel")
        .hide();
      this.$container = $(document.createElement("div")).addClass(
        "chat-container"
      );
      this.$element.append(this.$container);
      this.$app_element.append(this.$element);
      $("body").append(this.$app_element);
      this.bubble = new InstagramBubble(this);
      this.bubble.render();
      const navbarLabel = __("Show Instagram Chats");
      $("header.navbar > .container > .navbar-collapse > ul").prepend(`
        <li class='nav-item dropdown dropdown-notifications dropdown-mobile instagram-navbar-icon'>
          <button class="chat-channel-navbar-button chat-channel-navbar-button--instagram"
            id="instagram-chat-navbar-button" type="button"
            aria-controls="instagram-chat-panel" aria-expanded="false"
            aria-label="${navbarLabel}" title="${navbarLabel}">
            <i class='fa fa-instagram' aria-hidden='true'></i>
            <span class='badge' id='instagram-notification-count'></span>
          </button>
        </li>
      `);
      this.panel = new InstagramPanel({
        $wrapper: this.$container,
        config: config.message,
      });
      $(".instagram-navbar-icon").on("click", () => this.bubble.toggle());
      $(document).on("mouseup.instagram-chat", (event) => {
        if (!this.is_open) return;
        if (
          !this.$app_element.is(event.target) &&
          !this.$app_element.has(event.target).length &&
          !$(".instagram-navbar-icon").is(event.target) &&
          !$(".instagram-navbar-icon").has(event.target).length &&
          !$(".modal").is(event.target) &&
          !$(".modal").has(event.target).length
        ) {
          this.bubble.toggle();
        }
      });
    } catch (error) {
      console.error("Instagram Chat failed to initialize", error);
    }
  }

  set_navbar_expanded(expanded) {
    const label = expanded
      ? __("Close Instagram Chats")
      : __("Show Instagram Chats");
    $("#instagram-chat-navbar-button")
      .attr("aria-expanded", String(expanded))
      .attr("aria-label", label)
      .attr("title", label);
  }
};

$(function () {
  new frappe.InstagramChat();
});
