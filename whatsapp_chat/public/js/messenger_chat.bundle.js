import {
  MessengerBubble,
  MessengerList,
  get_settings,
  scroll_to_bottom,
} from './components';

frappe.provide('frappe.MessengerChat');
frappe.provide('frappe.MessengerChat.settings');

frappe.MessengerChat = class {
  constructor() {
    this.setup_app();
  }

  create_app() {
    this.$app_element = $(document.createElement('div'));
    this.$app_element.addClass('messenger-app');
    this.$messenger_container = $(document.createElement('div'));
    this.$messenger_container.addClass('chat-container');
    $('body').append(this.$app_element);
    this.is_open = false;

    this.$messenger_element = $(document.createElement('div'))
      .addClass('chat-element messenger-element')
      .attr('id', 'messenger-chat-panel')
      .hide();

    this.$messenger_element.append(`
      <span class="messenger-cross-button">
        ${frappe.utils.icon('close', 'lg')}
      </span>
    `);
    this.$messenger_element.append(this.$messenger_container);
    this.$messenger_element.appendTo(this.$app_element);

    this.messenger_bubble = new MessengerBubble(this);
    this.messenger_bubble.render();

    if (this.is_desk === true) {
      const navbar_label = __('Show Messenger Chats');
      $('header.navbar > .container > .navbar-collapse > ul').prepend(`
        <li class='nav-item dropdown dropdown-notifications dropdown-mobile messenger-navbar-icon'>
          <button class="chat-channel-navbar-button chat-channel-navbar-button--messenger"
            id="messenger-chat-navbar-button" type="button"
            aria-controls="messenger-chat-panel" aria-expanded="false"
            aria-label="${navbar_label}" title="${navbar_label}">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
              aria-hidden="true" focusable="false">
              <path d="M12 0C5.373 0 0 4.975 0 11.111c0 3.497 1.745 6.616 4.472 8.652V24l4.086-2.242c1.09.301 2.246.464 3.442.464 6.627 0 12-4.974 12-11.111S18.627 0 12 0zm1.194 14.963l-3.055-3.26-5.963 3.26L10.732 8l3.131 3.259L19.752 8l-6.558 6.963z"/>
            </svg>
            <span class="badge" id="messenger-notification-count"></span>
          </button>
        </li>
      `);
    }

    this.setup_events();
  }

  async setup_app() {
    try {
      this.is_desk = 'desk' in frappe;

      if (!this.is_desk && frappe.session && frappe.session.user === 'Guest') {
        return;
      }

      const res = await get_settings();
      this.is_admin = res.is_admin;

      if (this.is_desk && !(res.can_access_messenger ?? res.can_access_ui)) {
        return;
      }

      if (res.enable_chat === false) {
        return;
      }

      this.create_app();
      await frappe.socketio.init(res.socketio_port);

      frappe.MessengerChat.settings = {};
      frappe.MessengerChat.settings.user = res.user_settings;
      frappe.MessengerChat.settings.unread_count = 0;

      this.messenger_list = new MessengerList({
        $wrapper: this.$messenger_container,
        user: res.user,
        user_email: res.user_email,
        is_admin: res.is_admin,
      });
      this.messenger_list.render();
    } catch (error) {
      console.error(error);
    }
  }

  show_widget() {
    this.is_open = true;
    this.set_navbar_expanded(true);
    this.$messenger_element.fadeIn(250);
  }

  hide_widget() {
    this.is_open = false;
    this.set_navbar_expanded(false);
    this.$messenger_element.fadeOut(300);
  }

  set_navbar_expanded(expanded) {
    const label = expanded
      ? __('Close Messenger Chats')
      : __('Show Messenger Chats');
    $('#messenger-chat-navbar-button')
      .attr('aria-expanded', String(expanded))
      .attr('aria-label', label)
      .attr('title', label);
  }

  should_close(e) {
    const app = $('.messenger-app');
    const navbar = $('.navbar');
    const modal = $('.modal');
    return (
      !app.is(e.target) &&
      app.has(e.target).length === 0 &&
      !navbar.is(e.target) &&
      navbar.has(e.target).length === 0 &&
      !modal.is(e.target) &&
      modal.has(e.target).length === 0
    );
  }

  setup_events() {
    const me = this;
    $('.messenger-navbar-icon').on('click', function () {
      me.messenger_bubble.change_bubble();
    });

    $(document).mouseup(function (e) {
      if (me.should_close(e) && me.is_open === true) {
        me.messenger_bubble.change_bubble();
      }
    });
  }
};

$(function () {
  new frappe.MessengerChat();
});
