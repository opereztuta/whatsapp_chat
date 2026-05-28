export default class MessengerBubble {
  constructor(parent) {
    this.parent = parent;
    this.setup();
  }

  setup() {
    this.$messenger_bubble = $(document.createElement('div'));
    this.open_title = __('Show Messenger Chats');
    this.closed_title = __('Close Messenger Chat');

    const bubble_visible = this.parent.is_desk === true ? 'd-none' : '';
    this.open_inner_html = `
      <div class='p-3 chat-bubble ${bubble_visible}'>
        <span class='chat-message-icon'>
          <svg xmlns="http://www.w3.org/2000/svg" width="1.1rem" height="1.1rem" viewBox="0 0 24 24">
            <path d="M12 0C5.373 0 0 4.975 0 11.111c0 3.497 1.745 6.616 4.472 8.652V24l4.086-2.242c1.09.301 2.246.464 3.442.464 6.627 0 12-4.974 12-11.111S18.627 0 12 0zm1.194 14.963l-3.055-3.26-5.963 3.26L10.732 8l3.131 3.259L19.752 8l-6.558 6.963z"/>
          </svg>
        </span>
        <div>${this.open_title}</div>
      </div>
    `;
    this.closed_inner_html = `
      <div class='chat-bubble-closed chat-bubble ${bubble_visible}'>
        <span class='cross-icon'>
          ${frappe.utils.icon('close-alt', 'lg')}
        </span>
      </div>
    `;
    this.$messenger_bubble
      .attr({ title: this.open_title, id: 'messenger-bubble' })
      .html(this.open_inner_html);
  }

  render() {
    this.parent.$app_element.append(this.$messenger_bubble);
    this.setup_events();
  }

  change_bubble() {
    this.parent.is_open = !this.parent.is_open;
    if (this.parent.is_open === false) {
      this.$messenger_bubble
        .attr({ title: this.open_title })
        .html(this.open_inner_html);
      this.parent.hide_widget();
    } else {
      this.$messenger_bubble
        .attr({ title: this.closed_title })
        .html(this.closed_inner_html);
      this.parent.show_widget();
    }
  }

  setup_events() {
    const me = this;
    $('#messenger-bubble, .messenger-cross-button').on('click', () => {
      me.change_bubble();
    });
  }
}
