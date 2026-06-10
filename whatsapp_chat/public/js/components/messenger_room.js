import MessengerSpace from './messenger_space';
import { get_date_from_now, get_time, get_avatar_html, set_messenger_notification_count } from './chat_utils';

export default class MessengerRoom {
  constructor(opts) {
    this.$wrapper = opts.$wrapper;
    this.$rooms_container = opts.$rooms_container;
    this.messenger_list = opts.messenger_list;
    this.profile = opts.element;
    this.setup();
    if (!this.profile.is_read) {
      set_messenger_notification_count('increment');
    }
  }

  setup() {
    this.$messenger_room = $(document.createElement('div'));
    this.$messenger_room.addClass('chat-room');

    this.avatar_html = get_avatar_html(
      this.profile.room_type,
      this.profile.opposite_person_email,
      this.profile.room_name
    );

    const last_message = this.sanitize_last_message(this.profile.last_message);

    const info_html = `
      <div class='chat-profile-info'>
        <div class='chat-name'>
          ${__(this.profile.room_name)}
          <div class='chat-latest'
            style='display: ${this.profile.is_read ? 'none' : 'inline-block'}'
          ></div>
        </div>
        <div style='color: ${
          this.profile.is_read ? 'var(--text-muted)' : 'var(--text-color)'
        }' class='last-message'>${__(last_message)}</div>
      </div>
    `;
    const date_html = `
      <div class='chat-date'>
        ${__(get_date_from_now(this.profile.last_date, 'room'))}
      </div>
    `;

    this.$messenger_room.html(this.avatar_html + info_html + date_html);
  }

  sanitize_last_message(message) {
    let sanitized = $('<div>').text(message || '').html();
    if (sanitized && sanitized.length > 20) {
      sanitized = sanitized.substring(0, 20) + '...';
    }
    return sanitized;
  }

  set_as_read() {
    this.profile.is_read = 1;
    this.$messenger_room.find('.last-message').css('color', 'var(--text-muted)');
    this.$messenger_room.find('.chat-latest').hide();
    set_messenger_notification_count('decrement');
  }

  set_last_message(message, date) {
    const sanitized = this.sanitize_last_message(message);
    this.$messenger_room.find('.last-message').html(__(sanitized));
    this.$messenger_room.find('.chat-date').text(__(get_time(date)));
  }

  set_as_unread() {
    if (this.profile.is_read) {
      set_messenger_notification_count('increment');
    }
    this.profile.is_read = 0;
    this.$messenger_room.find('.last-message').css('color', 'var(--text-color)');
    this.$messenger_room.find('.chat-latest').show();
  }

  move_to_top() {
    this.$messenger_room.prependTo(this.$rooms_container);
  }

  render(mode) {
    if (mode === 'append') {
      this.$rooms_container.append(this.$messenger_room);
    } else {
      this.$rooms_container.prepend(this.$messenger_room);
    }
    this.setup_events();
  }

  setup_events() {
    this.$messenger_room.on('click', () => {
      if (typeof this.messenger_space !== 'undefined') {
        this.messenger_space.destroy_socket_events();
      }
      this.messenger_space = new MessengerSpace({
        $wrapper: this.$wrapper,
        messenger_list: this.messenger_list,
        profile: this.profile,
      });
      if (this.profile.is_read === 0) {
        frappe.call({
          method: 'whatsapp_chat.api.messenger.mark_as_read',
          args: { room: this.profile.room },
        });
        this.set_as_read();
      }
    });
  }
}
