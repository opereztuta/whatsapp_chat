import MessengerRoom from './messenger_room';
import { get_messenger_rooms, get_time, set_messenger_notification_count } from './chat_utils';

export default class MessengerList {
  constructor(opts) {
    this.$wrapper = opts.$wrapper;
    this.user = opts.user;
    this.user_email = opts.user_email;
    this.is_admin = opts.is_admin;
    this.setup();
  }

  setup() {
    this.$messenger_list = $(document.createElement('div'));
    this.$messenger_list.addClass('chat-list');
    this.setup_header();
    this.setup_search();
    this.fetch_and_setup_rooms();
    this.setup_socketio();
  }

  setup_header() {
    this.$messenger_list.append(`
      <div class='chat-list-header'>
        <h3>${__('Messenger Chats')}</h3>
      </div>
    `);
  }

  setup_search() {
    this.$messenger_list.append(`
      <div class='chat-search'>
        <div class='input-group'>
          <input class='form-control chat-search-box messenger-search-box'
            type='search'
            placeholder='${__('Search conversation')}'
          >
          <span class='search-icon'>
            ${frappe.utils.icon('search', 'sm')}
          </span>
        </div>
      </div>
    `);
  }

  async fetch_and_setup_rooms() {
    try {
      const res = await get_messenger_rooms();
      this.rooms = res;
      this.setup_rooms();
      this.render_messages();
    } catch (error) {
      frappe.msgprint({
        title: __('Error'),
        message: __('Something went wrong. Please refresh and try again.'),
      });
    }
  }

  setup_rooms() {
    this.$rooms_container = $(document.createElement('div'));
    this.$rooms_container.addClass('chat-rooms-container');
    this.messenger_rooms = [];

    this.rooms.forEach((element) => {
      const profile = {
        user: this.user,
        user_email: element.sender_id,
        last_message: element.last_message,
        last_date: element.modified,
        is_admin: this.is_admin,
        room: element.name,
        is_read: element.is_read,
        room_name: element.contact_name || element.sender_id,
        room_type: 'Guest',
        opposite_person_email: element.sender_id,
        channel: element.channel,
      };

      this.messenger_rooms.push([
        profile.room,
        new MessengerRoom({
          $wrapper: this.$wrapper,
          $rooms_container: this.$rooms_container,
          messenger_list: this,
          element: profile,
        }),
      ]);
    });

    this.$messenger_list.append(this.$rooms_container);
  }

  filter_rooms(query) {
    for (const room of this.messenger_rooms) {
      const txt = room[1].profile.room_name.toLowerCase();
      if (txt.includes(query)) {
        room[1].$messenger_room.show();
      } else {
        room[1].$messenger_room.hide();
      }
    }
  }

  create_new_room(profile) {
    this.messenger_rooms.unshift([
      profile.room,
      new MessengerRoom({
        $wrapper: this.$wrapper,
        $rooms_container: this.$rooms_container,
        messenger_list: this,
        element: profile,
      }),
    ]);
    this.messenger_rooms[0][1].render('prepend');
  }

  render_messages() {
    this.$rooms_container.empty();
    for (const element of this.messenger_rooms) {
      element[1].render('append');
    }
  }

  render() {
    this.$wrapper.html(this.$messenger_list);
    this.setup_events();
  }

  move_room_to_top(room_item) {
    this.messenger_rooms = [
      room_item,
      ...this.messenger_rooms.filter((item) => item !== room_item),
    ];
  }

  truncate_preview(message) {
    const safe = message || '';
    return safe.length > 24 ? safe.substring(0, 24) + '...' : safe;
  }

  setup_events() {
    const me = this;
    this.$messenger_list.find('.messenger-search-box').on('input', function () {
      me.filter_rooms($(this).val().toLowerCase());
    });
  }

  setup_socketio() {
    const me = this;
    frappe.realtime.on('latest_messenger_updates', function (res) {
      let room_item = me.messenger_rooms.find((el) => el[0] === res.room);

      if (typeof room_item === 'undefined') {
        const preview = me.truncate_preview(res.preview || res.content || '');
        const profile = {
          user: me.user,
          user_email: res.sender_user_no,
          last_message: preview,
          last_date: res.creation,
          is_admin: me.is_admin,
          room: res.room,
          is_read: 0,
          room_name: res.contact_name,
          room_type: 'Guest',
          opposite_person_email: res.sender_user_no,
          channel: res.channel,
        };
        me.create_new_room(profile);
        room_item = me.messenger_rooms[0];
      }

      const message = me.truncate_preview(res.preview || res.content || '');
      room_item[1].set_last_message(message, res.creation);
      if (res.media_update) return;

      frappe.utils.play_sound('chat-message-receive');

      if (me.$messenger_list.is(':visible')) {
        room_item[1].set_as_unread();
        room_item[1].move_to_top();
        me.move_room_to_top(room_item);
      } else if ($('.messenger-element .chat-space').is(':visible')) {
        frappe.call({
          method: 'whatsapp_chat.api.messenger.mark_as_read',
          args: { room: res.room },
        });
      } else {
        if (room_item[1].profile.is_read === 1) {
          set_messenger_notification_count('increment');
          room_item[1].profile.is_read = 0;
        }
      }
    });
  }
}
