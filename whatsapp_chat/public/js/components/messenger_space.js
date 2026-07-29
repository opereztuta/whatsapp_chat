import {
  get_time,
  scroll_to_bottom,
  get_messenger_messages,
  send_messenger_message,
  get_date_from_now,
  is_date_change,
  get_avatar_html,
  get_error_message,
  upload_chat_file,
} from './chat_utils';

export default class MessengerSpace {
  constructor(opts) {
    this.messenger_list = opts.messenger_list;
    this.$wrapper = opts.$wrapper;
    this.profile = opts.profile;
    this.setup();
  }

  setup() {
    this.$chat_space = $(document.createElement('div'));
    this.$chat_space.addClass('chat-space');
    this.setup_header();
    this.fetch_and_setup_messages();
    this.setup_socketio();
  }

  setup_header() {
    const avatar_html = get_avatar_html(
      this.profile.room_type,
      this.profile.opposite_person_email,
      this.profile.room_name
    );
    this.$chat_space.append(`
      <div class='chat-header'>
        <span class='messenger-back-button' title='${__('Go Back')}'>
          ${frappe.utils.icon('left')}
        </span>
        ${avatar_html}
        <div class='chat-profile-info'>
          <div class='chat-profile-name'>${__(this.profile.room_name)}</div>
          <div class='chat-profile-status'></div>
        </div>
      </div>
    `);
  }

  setup_actions() {
    this.$chat_actions = $(document.createElement('div'));
    this.$chat_actions.addClass('chat-space-actions');
    const accept = (this.profile.channel || '').toLowerCase() === 'instagram'
      ? 'image/*,video/mp4'
      : 'image/*,audio/*,video/mp4,video/3gp,application/pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx';
    this.$chat_actions.html(`
      <div class='messenger-message-composer'>
        <span class='messenger-open-attach' title='${__('Attach file')}'>
          ${frappe.utils.icon('attachment', 'lg')}
        </span>
        <input type='file' class='messenger-file-uploader'
          accept='${accept}' style='display: none;'>
        <input class='form-control type-message'
          type='text'
          placeholder='${__('Type message')}'
        >
        <div>
          <span class='message-send-button'>
            <svg xmlns="http://www.w3.org/2000/svg" width="1.1rem" height="1.1rem" viewBox="0 0 24 24">
              <path d="M24 0l-6 22-8.129-7.239 7.802-8.234-10.458 7.227-7.215-1.754 24-12zm-15 16.668v7.332l3.258-4.431-3.258-2.901z"/>
            </svg>
          </span>
        </div>
      </div>
    `);
    this.$chat_space.append(this.$chat_actions);
  }

  async fetch_and_setup_messages() {
    try {
      const res = await get_messenger_messages(this.profile.room);
      this.setup_messages(res);
      this.setup_actions();
      this.render();
    } catch (error) {
      frappe.msgprint({
        title: __('Error'),
        message: __('Something went wrong. Please refresh and try again.'),
      });
    }
  }

  setup_messages(messages_list) {
    this.$chat_space_container = $(document.createElement('div'));
    this.$chat_space_container.addClass('chat-space-container');
    this.make_messages_html(messages_list);
    this.$chat_space_container.html(this.message_html);
    this.$chat_space.append(this.$chat_space_container);
  }

  make_messages_html(messages_list) {
    this.prevMessage = {};
    this.message_html = '';
    messages_list.forEach((element) => {
      this.message_html += this.make_date_line_html(element.creation);
      const message_type = element.direction === 'outgoing' ? 'recipient' : 'sender';
      this.message_html += this.make_message(
        element.content,
        get_time(element.creation),
        message_type,
        element.content_type,
        element.attachment_mime_type,
        element.attachment_name,
        element.attachment_status,
        element.name,
        element.provider_attachment_url
      ).prop('outerHTML');
      this.prevMessage = element;
    });
  }

  make_date_line_html(dateObj) {
    const html = `
      <div class='date-line'>
        <span>${__(get_date_from_now(dateObj, 'space'))}</span>
      </div>
    `;
    if ($.isEmptyObject(this.prevMessage)) return html;
    if (is_date_change(dateObj, this.prevMessage.creation)) return html;
    return '';
  }

  make_message(
    content,
    time,
    type,
    content_type,
    attachment_mime_type,
    attachment_name,
    attachment_status,
    message_name,
    provider_attachment_url
  ) {
    const message_class = type === 'recipient' ? 'recipient-message' : 'sender-message';
    const $el = $(document.createElement('div')).addClass(message_class);
    if (message_name) $el.attr('data-message-name', message_name);
    const $bubble = $(document.createElement('div')).addClass('message-bubble');

    const safe_content = content || '';
    const normalized_type = content_type || 'text';
    let derived_name = '';
    try {
      derived_name = decodeURIComponent(
        new URL(safe_content, window.location.origin).pathname.split('/').pop()
      );
    } catch (error) {
      derived_name = safe_content.split('/').pop().split('?')[0];
    }
    const file_name = attachment_name || derived_name || __('Attachment');
    const is_url = (
      safe_content.startsWith('/files/')
      || safe_content.startsWith('/private/files/')
      || safe_content.startsWith(
        '/api/method/whatsapp_chat.api.messenger.download_attachment'
      )
      || safe_content.startsWith('http://')
      || safe_content.startsWith('https://')
    );

    let $content;
    if (attachment_status === 'Pending') {
      $content = $(document.createElement('span'))
        .addClass('text-muted')
        .text(__('Attachment processing…'));
    } else if (attachment_status === 'Failed') {
      $content = $(document.createElement('div'))
        .addClass('text-muted')
        .append($(document.createElement('span')).text(__('Attachment unavailable')));
      if (provider_attachment_url) {
        $content.append(' ').append(
          $(document.createElement('a'))
            .attr({
              href: provider_attachment_url,
              target: '_blank',
              rel: 'noopener noreferrer',
            })
            .text(__('Open provider copy'))
        );
      }
    } else if (normalized_type === 'audio' && safe_content) {
      const $audio = $(document.createElement('audio'))
        .attr({ controls: true, preload: 'metadata', src: safe_content });
      if (attachment_mime_type) $audio.attr('type', attachment_mime_type);
      $content = $(document.createElement('div'))
        .addClass('chat-audio-message')
        .append(
          $(document.createElement('div')).addClass('chat-audio-label').text(__('Audio'))
        )
        .append($audio);
    } else if (is_url && file_name && normalized_type !== 'text') {
      if (normalized_type === 'image') {
        $content = $(document.createElement('img'))
          .attr({ src: safe_content })
          .addClass('img-responsive chat-image');
        $bubble.css({ padding: '0px', background: 'inherit' });
      } else if (normalized_type === 'video') {
        $content = $(document.createElement('video'))
          .attr({ controls: true, preload: 'metadata', src: safe_content })
          .addClass('chat-video');
      } else {
        $content = $(document.createElement('a'))
          .attr({
            href: safe_content,
            target: '_blank',
            rel: 'noopener noreferrer',
          })
          .text(file_name);
        if (type === 'sender') $content.css('color', 'var(--cyan-100)');
      }
    } else {
      $content = $(document.createElement('span')).text(safe_content);
    }

    $bubble.append($content);
    $el.append($bubble);
    $el.append($(document.createElement('div')).addClass('message-time').text(time));
    return $el;
  }

  setup_socketio() {
    const me = this;
    this.received_ids = new Set();

    const receive = function (res) {
      if (res.room !== me.profile.room) return;
      const id = res.name || `${res.content}-${res.creation}`;
      const $message = me.make_message(
        res.content,
        get_time(res.creation),
        'sender',
        res.content_type,
        res.attachment_mime_type,
        res.attachment_name,
        res.attachment_status,
        res.name,
        res.provider_attachment_url
      );
      if (res.media_update && res.name) {
        const $existing = me.$chat_space_container
          .find('[data-message-name]')
          .filter(function () {
            return $(this).attr('data-message-name') === res.name;
          });
        if ($existing.length) {
          $existing.replaceWith($message);
          scroll_to_bottom(me.$chat_space_container);
          return;
        }
      }
      if (me.received_ids.has(id)) return;
      me.received_ids.add(id);
      me.$chat_space_container.append($message);
      scroll_to_bottom(me.$chat_space_container);
    };

    frappe.realtime.on('latest_messenger_updates', receive);

    frappe.realtime.on(this.profile.room, function (res) {
      if (!res.messenger) return;
      receive(res);
    });
  }

  destroy_socket_events() {
    frappe.realtime.off('latest_messenger_updates');
    frappe.realtime.off(this.profile.room);
  }

  render() {
    this.$wrapper.html(this.$chat_space);
    this.setup_events();
    scroll_to_bottom(this.$chat_space_container);
  }

  async handle_send_message() {
    const $input = this.$chat_space.find('.type-message');
    const content = ($input.val() || '').trim();
    if (!content) return;

    try {
      const sent = await send_messenger_message(this.profile.room, content);
      $input.val('');
      this.$chat_space_container.append(
        this.make_message(
          sent.content,
          get_time(),
          'recipient',
          'text',
          null,
          null,
          null,
          sent.name,
          null
        )
      );
      scroll_to_bottom(this.$chat_space_container);
    } catch (error) {
      frappe.msgprint({
        title: __('Could not send message'),
        message: get_error_message(error, __('Something went wrong. Please refresh and try again.')),
        indicator: 'red',
      });
    }
  }

  async handle_upload_file(file) {
    const $attach = this.$chat_space.find('.messenger-open-attach');
    $attach.addClass('disabled');
    try {
      const file_doc = await upload_chat_file(
        file,
        'Messenger Contact',
        this.profile.room,
        true
      );
      const sent = await send_messenger_message(
        this.profile.room,
        '',
        file_doc.file_url,
        file.type
      );
      this.$chat_space_container.append(
        this.make_message(
          sent.content,
          get_time(),
          'recipient',
          sent.content_type,
          sent.attachment_mime_type,
          sent.attachment_name,
          sent.attachment_status,
          sent.name,
          null
        )
      );
      scroll_to_bottom(this.$chat_space_container);
    } finally {
      $attach.removeClass('disabled');
    }
  }

  setup_events() {
    const me = this;
    this.$chat_space.find('.messenger-back-button').on('click', function () {
      me.messenger_list.render_messages();
      me.messenger_list.render();
    });
    this.$chat_space.find('.message-send-button').on('click', function () {
      me.handle_send_message();
    });
    this.$chat_space.find('.messenger-open-attach').on('click', function () {
      if (!$(this).hasClass('disabled')) {
        me.$chat_space.find('.messenger-file-uploader').click();
      }
    });
    this.$chat_space.find('.messenger-file-uploader').on('change', function () {
      const file = this.files && this.files[0];
      if (!file) return;
      me.handle_upload_file(file).catch((error) => {
        frappe.msgprint({
          title: __('Could not send attachment'),
          message: get_error_message(
            error,
            __('Could not upload or send this attachment.')
          ),
          indicator: 'red',
        });
      }).finally(() => {
        this.value = '';
      });
    });
    this.$chat_space.find('.type-message').on('keydown', function (e) {
      if (e.which === 13) me.handle_send_message();
    });
  }
}
