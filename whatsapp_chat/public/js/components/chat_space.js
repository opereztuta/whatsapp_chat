import {
  get_time,
  scroll_to_bottom,
  get_messages,
  get_date_from_now,
  is_date_change,
  send_message,
  send_voice_note,
  get_call_state,
  start_whatsapp_call,
  is_image,
  get_avatar_html,
  mark_message_read,
  get_error_message,
} from './chat_utils';

export default class ChatSpace {
  constructor(opts) {
    this.chat_list = opts.chat_list;
    this.$wrapper = opts.$wrapper;
    this.profile = opts.profile;
    this.file = null;
    this.voice_recorder = null;
    this.voice_stream = null;
    this.voice_chunks = [];
    this.voice_mime_type = null;
    this.voice_timer = null;
    this.voice_recording_started_at = null;
    this.voice_should_send = false;
    this.call_state = null;
    this.setup();
  }

  setup() {
    this.$chat_space = $(document.createElement('div'));
    this.typing = false;
    this.$chat_space.addClass('chat-space');
    this.setup_header();
    this.fetch_and_setup_messages();
    this.setup_socketio();
  }

  setup_header() {
    this.avatar_html = get_avatar_html(
      this.profile.room_type,
      this.profile.opposite_person_email,
      this.profile.room_name
    );
    const header_html = `
			<div class='chat-header'>
				${
          this.profile.is_admin === true
            ? `<span class='chat-back-button' title='${__('Go Back')}' >
								${frappe.utils.icon('left')}
							</span>`
            : ``
        }
				${this.avatar_html}
				<div class='chat-profile-info'>
					<div class='chat-profile-name'>
					${__(this.profile.room_name)}
					<div class='online-circle'></div>
					</div>
					<div class='chat-profile-status'>${__('Typing...')}</div>
				</div>
			</div>
		`;
    this.$chat_space.append(header_html);
  }

  async fetch_and_setup_messages() {
    try {
      const res = await get_messages(
        this.profile.room
      );
      this.setup_messages(res);
      this.setup_actions();
      this.render();
      this.refresh_call_state();

      // Mark messages as read when viewing the chat
      // This will also send read receipts to WhatsApp if enabled in settings
      mark_message_read(this.profile.room);
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
    this.message_html = ``;
    if (this.profile.message) {
      messages_list.push(this.profile.message);
      send_message(this.profile.message.content, this.profile.room, null);
    }
    messages_list.forEach((element) => {
      const date_line_html = this.make_date_line_html(element.creation);
      this.message_html += date_line_html;

      let message_type = 'sender';

      if (element.sender_user_no === this.profile.user_email) {
        message_type = 'recipient';
      } else if (this.profile.room_type === 'Guest') {
        if (this.profile.is_admin === true && element.sender !== 'Guest') {
          message_type = 'recipient';
        }
      }
      this.message_html += this.make_message(
        element.content,
        get_time(element.creation),
        message_type,
        element.sender,
        element.caption,
        element.content_type,
        element.attachment_mime_type,
        element.is_voice_note
      ).prop('outerHTML');

      this.prevMessage = element;
    });
  }

  make_date_line_html(dateObj) {
    let result = `
			<div class='date-line'>
				<span>
					${__(get_date_from_now(dateObj, 'space'))}
				</span>
			</div>
		`;
    if ($.isEmptyObject(this.prevMessage)) {
      return result;
    } else if (is_date_change(dateObj, this.prevMessage.creation)) {
      return result;
    } else {
      return '';
    }
  }

  setup_actions() {
    this.$chat_actions = $(document.createElement('div'));
    this.$chat_actions.addClass('chat-space-actions');
    const chat_actions_html = `
			<span class='open-attach-items'>
				${frappe.utils.icon('attachment', 'lg')}
			</span>
			<button type='button' class='whatsapp-call-button disabled' title='${__('Checking call availability')}'>
				${frappe.utils.icon('es-line-call', 'md')}
			</button>
			<input type='file' id='chat-file-uploader'
				accept='image/*,audio/*,video/mp4,video/3gp,application/pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx'
				style='display: none;'
			>
			<input class='form-control type-message'
				type='search'
				placeholder='${__('Type message')}'
			>
			<div class='voice-recording-state hidden'>
				<span class='voice-recording-dot'></span>
				<span class='voice-recording-timer'>0:00</span>
				<button type='button' class='voice-stop-button' title='${__('Send voice note')}'>
					<svg xmlns="http://www.w3.org/2000/svg" width="1.1rem" height="1.1rem" viewBox="0 0 24 24">
						<path d="M24 0l-6 22-8.129-7.239 7.802-8.234-10.458 7.227-7.215-1.754 24-12zm-15 16.668v7.332l3.258-4.431-3.258-2.901z"/>
					</svg>
				</button>
				<button type='button' class='voice-cancel-button' title='${__('Cancel recording')}'>
					${frappe.utils.icon('es-line-delete', 'md')}
				</button>
			</div>
			<button type='button' class='voice-record-button' title='${__('Record voice note')}'>
				${frappe.utils.icon('es-solid-audio', 'md')}
			</button>
			<div>
				<span class='message-send-button'>
					<svg xmlns="http://www.w3.org/2000/svg" width="1.1rem" height="1.1rem" viewBox="0 0 24 24">
						<path d="M24 0l-6 22-8.129-7.239 7.802-8.234-10.458 7.227-7.215-1.754 24-12zm-15 16.668v7.332l3.258-4.431-3.258-2.901z"/>
					</svg>
				</span>
			</div>
		`;
    this.$chat_actions.html(chat_actions_html);
    this.$chat_space.append(this.$chat_actions);
  }

  async handle_upload_file(file) {
    file.name = file.file_obj.name;
    const file_doc = await this.upload_file(file);
    return this.handle_send_message(file_doc.file_url, file.file_obj.type);
  }

  upload_file(file) {
    return new Promise((resolve, reject) => {
      let xhr = new XMLHttpRequest();

      xhr.addEventListener('error', () => {
        reject(new Error(__('Internal Server Error')));
      });
      xhr.onreadystatechange = () => {
        if (xhr.readyState == XMLHttpRequest.DONE) {
          if (xhr.status === 200) {
            let r = null;
            let file_doc = null;
            try {
              r = JSON.parse(xhr.responseText);
              if (r.message.doctype === 'File') {
                file_doc = r.message;
              }
            } catch (e) {
              r = xhr.responseText;
            }
            if (file_doc === null) {
              reject(new Error(__('File upload failed!')));
              return;
            }
            resolve(file_doc);
          } else {
            try {
              const error = JSON.parse(xhr.responseText);
              const messages = JSON.parse(error._server_messages);
              const errorObj = JSON.parse(messages[0]);
              reject(new Error(__(errorObj.message)));
            } catch (e) {
              reject(new Error(__('File upload failed!')));
            }
          }
        }
      };

      xhr.open('POST', '/api/method/upload_file', true);
      xhr.setRequestHeader('Accept', 'application/json');
      xhr.setRequestHeader('X-Frappe-CSRF-Token', frappe.csrf_token);

      let form_data = new FormData();

      form_data.append('file', file.file_obj, file.name);
      form_data.append('is_private', +false);

      form_data.append('doctype', 'WhatsApp Contact');
      form_data.append('docname', this.profile.room);
      form_data.append('optimize', +true);
      xhr.send(form_data);
    });
  }

  setup_events() {
    const me = this;

    //Timeout function
    me.typing_timeout = () => {
      me.typing = false;
    };

    $('.chat-back-button').on('click', function () {
      me.chat_list.render_messages();
      me.chat_list.render();
    });

    $('.open-attach-items').on('click', function () {
      if ($(this).hasClass('disabled')) {
        return;
      }
      $('#chat-file-uploader').click();
    });

    $('.whatsapp-call-button').on('click', function () {
      if ($(this).hasClass('disabled') || $(this).hasClass('loading')) {
        return;
      }
      me.handle_start_call();
    });

    $('#chat-file-uploader').on('change', function () {
      if (this.files.length > 0) {
        me.file = {};
        me.file.file_obj = this.files[0];
        me.handle_upload_file(me.file).catch((error) => {
          frappe.msgprint({
            title: __('Error'),
            message: get_error_message(
              error,
              __('Could not upload or send this attachment.')
            ),
            indicator: 'red',
          });
        }).finally(() => {
          me.file = null;
          this.value = '';
        });
      }
    });

    $('.message-send-button').on('click', function () {
      if ($(this).hasClass('disabled')) {
        return;
      }
      me.handle_send_message();
    });

    $('.voice-record-button').on('click', function () {
      me.start_voice_recording();
    });

    $('.voice-stop-button').on('click', function () {
      me.stop_voice_recording(true);
    });

    $('.voice-cancel-button').on('click', function () {
      me.stop_voice_recording(false);
    });

    $('.type-message').keydown(function (e) {
      if (e.which === 13) {
        me.handle_send_message();
      }
    });
  }

  get_recording_mime_type() {
    if (typeof MediaRecorder === 'undefined') {
      return null;
    }

    const preferred_types = [
      'audio/ogg;codecs=opus',
      'audio/mp4',
      'audio/webm;codecs=opus',
    ];

    for (const mime_type of preferred_types) {
      if (MediaRecorder.isTypeSupported(mime_type)) {
        return mime_type;
      }
    }

    return '';
  }

  get_voice_file_extension(mime_type) {
    const normalized = (mime_type || '').split(';')[0].toLowerCase();
    if (normalized === 'audio/mp4') {
      return 'm4a';
    }
    if (normalized === 'audio/webm') {
      return 'webm';
    }
    return 'ogg';
  }

  update_voice_recording_timer() {
    if (!this.voice_recording_started_at) {
      return;
    }

    const elapsed_seconds = Math.floor(
      (Date.now() - this.voice_recording_started_at) / 1000
    );
    const minutes = Math.floor(elapsed_seconds / 60);
    const seconds = `${elapsed_seconds % 60}`.padStart(2, '0');
    $('.voice-recording-timer').text(`${minutes}:${seconds}`);
  }

  set_recording_ui(is_recording) {
    $('.type-message').prop('disabled', is_recording);
    $('.open-attach-items').toggleClass('disabled', is_recording);
    $('.message-send-button').toggleClass('disabled', is_recording);
    $('.voice-record-button').toggleClass('hidden', is_recording);
    $('.voice-recording-state').toggleClass('hidden', !is_recording);
  }

  cleanup_voice_recording() {
    if (this.voice_timer) {
      clearInterval(this.voice_timer);
      this.voice_timer = null;
    }
    if (this.voice_stream) {
      this.voice_stream.getTracks().forEach((track) => track.stop());
    }
    this.voice_recorder = null;
    this.voice_stream = null;
    this.voice_chunks = [];
    this.voice_mime_type = null;
    this.voice_recording_started_at = null;
    this.voice_should_send = false;
    $('.voice-recording-timer').text('0:00');
    this.set_recording_ui(false);
  }

  async start_voice_recording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      frappe.msgprint({
        title: __('Voice recording unavailable'),
        message: __('This browser does not support microphone recording.'),
        indicator: 'red',
      });
      return;
    }

    const mime_type = this.get_recording_mime_type();
    if (mime_type === null) {
      frappe.msgprint({
        title: __('Voice recording unavailable'),
        message: __('This browser does not support audio recording.'),
        indicator: 'red',
      });
      return;
    }

    try {
      this.voice_stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });
      this.voice_chunks = [];
      this.voice_mime_type = mime_type;
      this.voice_should_send = false;

      const options = mime_type ? { mimeType: mime_type } : {};
      this.voice_recorder = new MediaRecorder(this.voice_stream, options);
      this.voice_recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          this.voice_chunks.push(event.data);
        }
      };
      this.voice_recorder.onstop = () => {
        this.finish_voice_recording();
      };
      this.voice_recorder.start();
      this.voice_recording_started_at = Date.now();
      this.update_voice_recording_timer();
      this.voice_timer = setInterval(() => {
        this.update_voice_recording_timer();
      }, 1000);
      this.set_recording_ui(true);
    } catch (error) {
      this.cleanup_voice_recording();
      frappe.msgprint({
        title: __('Microphone permission needed'),
        message: __('Allow microphone access to record a voice note.'),
        indicator: 'red',
      });
    }
  }

  stop_voice_recording(should_send) {
    if (!this.voice_recorder) {
      return;
    }

    this.voice_should_send = should_send;
    if (this.voice_recorder.state !== 'inactive') {
      this.voice_recorder.stop();
    } else {
      this.finish_voice_recording();
    }
  }

  async finish_voice_recording() {
    const should_send = this.voice_should_send;
    const chunks = this.voice_chunks;
    const mime_type = this.voice_mime_type || (
      chunks[0] ? chunks[0].type : ''
    );
    this.cleanup_voice_recording();

    if (!should_send) {
      return;
    }

    if (!chunks.length) {
      frappe.msgprint({
        title: __('Empty voice note'),
        message: __('No audio was recorded.'),
        indicator: 'red',
      });
      return;
    }

    const blob = new Blob(chunks, { type: mime_type || 'audio/ogg' });
    const extension = this.get_voice_file_extension(blob.type || mime_type);
    const file = new File(
      [blob],
      `voice-note-${Date.now()}.${extension}`,
      { type: blob.type || mime_type }
    );

    try {
      const file_doc = await this.upload_file({
        file_obj: file,
        name: file.name,
      });
      const sent = await send_voice_note(
        this.profile.room,
        file_doc.file_url,
        file.type || mime_type
      );
      this.append_outgoing_message(sent);
    } catch (error) {
      frappe.msgprint({
        title: __('Could not send voice note'),
        message: get_error_message(
          error,
          __('This voice note could not be sent.')
        ),
        indicator: 'red',
      });
    }
  }

  setup_socketio() {
    const me = this;
    // Track received message IDs to prevent duplicates
    this.received_message_ids = new Set();
    this.received_call_event_ids = new Set();

    // Listen for room-specific messages
    frappe.realtime.on(this.profile.room, function (res) {
      me.handle_incoming_message(res);
    });

    // Also listen for latest_chat_updates and filter by room
    frappe.realtime.on('latest_chat_updates', function (res) {
      if (res.room === me.profile.room) {
        me.handle_incoming_message(res);
      }
    });

    frappe.realtime.on('whatsapp_call_update', function (res) {
      if (res.room === me.profile.room) {
        me.handle_call_update(res);
      }
    });
  }

  handle_incoming_message(res) {
    // Create a unique ID for the message to prevent duplicates
    const msg_id = res.name || `${res.content}-${res.creation}-${res.sender_user_no}`;

    // Skip if we've already processed this message
    if (this.received_message_ids.has(msg_id)) {
      return;
    }
    this.received_message_ids.add(msg_id);

    // Display the message
    this.receive_message(res, get_time(res.creation));

    // Mark as read since chat is open and user is viewing it
    mark_message_read(this.profile.room);
  }

  destroy_socket_events() {
    frappe.realtime.off(this.profile.room);
    frappe.realtime.off('latest_chat_updates');
    frappe.realtime.off('whatsapp_call_update');
  }

  set_call_button_state(state) {
    const $button = $('.whatsapp-call-button');
    if (!$button.length) {
      return;
    }

    const status = state ? state.status : 'Disabled';
    const message = state ? state.message : __('WhatsApp calling unavailable');
    $button
      .removeClass('disabled waiting ready loading')
      .attr('title', message || __('Call on WhatsApp'));

    if (status === 'Ready' || status === 'No Permission') {
      $button.addClass('ready');
      return;
    }

    if (status === 'Permission Requested') {
      $button.addClass('disabled waiting');
      return;
    }

    $button.addClass('disabled');
  }

  async refresh_call_state() {
    try {
      const state = await get_call_state(this.profile.room);
      this.call_state = state;
      this.set_call_button_state(state);
    } catch (error) {
      this.call_state = null;
      this.set_call_button_state({
        status: 'Disabled',
        message: get_error_message(
          error,
          __('WhatsApp calling unavailable')
        ),
      });
    }
  }

  append_call_event(message, status) {
    const $event = $(document.createElement('div')).addClass(
      'chat-call-event'
    );
    if (status) {
      $event.attr('data-status', status);
    }
    $event.text(message || __('Call status updated'));
    this.$chat_space_container.append($event);
    scroll_to_bottom(this.$chat_space_container);
  }

  handle_call_update(res) {
    const event_id = `${res.call || ''}-${res.status || ''}-${res.creation || ''}`;
    if (this.received_call_event_ids.has(event_id)) {
      return;
    }
    this.received_call_event_ids.add(event_id);
    this.append_call_event(res.content, res.status);
    this.refresh_call_state();
  }

  async handle_start_call() {
    const $button = $('.whatsapp-call-button');
    $button.addClass('loading disabled');

    try {
      const result = await start_whatsapp_call(this.profile.room);
      this.append_call_event(result.message, result.status);
      await this.refresh_call_state();
    } catch (error) {
      this.set_call_button_state(this.call_state);
      frappe.msgprint({
        title: __('Could not start WhatsApp call'),
        message: get_error_message(
          error,
          __('The call could not be started.')
        ),
        indicator: 'red',
      });
    } finally {
      $button.removeClass('loading');
    }
  }

  get_typing_changes(res) {
    if (res.user != this.profile.user_email) {
      if (
        (this.profile.is_admin === true && res.is_guest === 'true') ||
        this.profile.is_admin === false ||
        this.profile.room_type === 'Group' ||
        this.profile.room_type === 'Direct'
      ) {
        if (res.is_typing === 'false') {
          $('.chat-profile-status').css('visibility', 'hidden');
        } else {
          $('.chat-profile-status').css('visibility', 'visible');
          const timeout = setTimeout(() => {
            $('.chat-profile-status').css('visibility', 'hidden');
          }, 3000);
        }
      }
    }
  }

  make_message(
    content,
    time,
    type,
    name,
    caption,
    content_type,
    attachment_mime_type,
    is_voice_note
  ) {
    const message_class =
      type === 'recipient' ? 'recipient-message' : 'sender-message';
    const $recipient_element = $(document.createElement('div')).addClass(
      message_class
    );
    const $message_element = $(document.createElement('div')).addClass(
      'message-bubble'
    );

    const $name_element = $(document.createElement('div'))
      .addClass('message-name')
      .text(name || '');

    const safe_content = content || '';
    const normalized_content_type = content_type || 'text';
    const n = safe_content.lastIndexOf('/');
    const file_name = safe_content.substring(n + 1) || '';
    const is_attachment_url = (
      safe_content.startsWith('/files/')
      || safe_content.startsWith('/private/files/')
      || safe_content.startsWith('http://')
      || safe_content.startsWith('https://')
    );
    let $sanitized_content;

    if (normalized_content_type === 'audio' && safe_content) {
      const $audio = $(document.createElement('audio'));
      $audio.attr({
        controls: true,
        preload: 'metadata',
        src: safe_content,
      });
      if (attachment_mime_type) {
        $audio.attr('type', attachment_mime_type);
      }

      const $audio_label = $(document.createElement('div'))
        .addClass('chat-audio-label')
        .text(is_voice_note || !caption ? __('Voice note') : __('Audio'));

      $sanitized_content = $(document.createElement('div'))
        .addClass('chat-audio-message')
        .append($audio_label)
        .append($audio);
    } else if (
      is_attachment_url
      && file_name !== ''
      && normalized_content_type !== 'text'
    ) {
      let $url;
      if (normalized_content_type === 'image' || is_image(file_name)) {
        $url = $(document.createElement('img'));
        $url.attr({ src: safe_content }).addClass('img-responsive chat-image');
        $message_element.css({ padding: '0px', background: 'inherit' });
        $name_element.css({
          color: 'var(--text-muted)',
          'padding-bottom': 'var(--padding-xs)',
        });
      } else {
        $url = $(document.createElement('a'));
        $url.attr({ href: safe_content, target: '_blank' }).text(file_name);

        if (type === 'sender') {
          $url.css('color', 'var(--cyan-100)');
        }
      }
      $sanitized_content = $url;
    } else {
      $sanitized_content = $(document.createElement('span'))
        .text(safe_content);
    }

    if (type === 'sender' && this.profile.room_type === 'Group') {
      $message_element.append($name_element);
    }
    $message_element.append($sanitized_content);

    // Add caption below image/media if present
    if (caption) {
      const $caption_element = $(document.createElement('div'))
        .addClass('message-caption')
        .css({
          'padding': 'var(--padding-sm)',
          'font-size': 'var(--text-sm)',
          'color': type === 'sender' ? 'var(--white)' : 'var(--text-color)',
          'background': type === 'sender' ? 'var(--primary-color)' : 'var(--control-bg)',
          'border-radius': '0 0 13px 13px',
        })
        .text(caption);
      $message_element.append($caption_element);
    }

    $recipient_element.append($message_element);
    $recipient_element.append(
      $(document.createElement('div')).addClass('message-time').text(time)
    );

    return $recipient_element;
  }

  append_outgoing_message(message) {
    const content = message.content || '';
    this.$chat_space_container.append(
      this.make_message(
        content,
        get_time(),
        'recipient',
        this.profile.user,
        message.caption,
        message.content_type,
        message.attachment_mime_type,
        message.is_voice_note
      )
    );
    scroll_to_bottom(this.$chat_space_container);
  }

  async handle_send_message(attachment, mime_type, content_type) {
    const $type_message = $('.type-message');
    let content = ($type_message.val() || '').trim();

    if (!attachment && content.length === 0) {
      return;
    }
    this.typing = false;
    if (this.timeout) {
      clearTimeout(this.timeout);
    }

    if (
      this.profile.is_admin === true &&
      frappe.Chat.settings.user.enable_message_tone === 1
    ) {
      frappe.utils.play_sound('chat-message-send');
    }

    try {
      const sent = await send_message(
        content,
        this.profile.room,
        attachment,
        mime_type,
        content_type
      );
      this.append_outgoing_message(sent);
      $type_message.val('');
    } catch (error) {
      frappe.msgprint({
        title: __('Could not send message'),
        message: get_error_message(
          error,
          __('Something went wrong. Please refresh and try again.')
        ),
        indicator: 'red',
      });
    }
  }

  receive_message(res, time) {
    let chat_type = 'sender';
    // Skip if this is our own outgoing message (sender_user_no would be empty or 'Administrator' for outgoing)
    if (res.sender_user_no === 'Administrator' || res.sender_user_no === this.profile.user) {
      return;
    }

    if (
      this.profile.is_admin === true &&
      $('.chat-element').is(':visible') &&
      frappe.Chat.settings.user.enable_message_tone === 1
    ) {
      frappe.utils.play_sound('chat-message-receive');
    }

    if (this.profile.room_type === 'Guest') {
      if (this.profile.is_admin === true && res.user !== 'Guest') {
        chat_type = 'recipient';
      }
    }

    this.$chat_space_container.append(
      this.make_message(
        res.content,
        time,
        chat_type,
        res.user,
        res.caption,
        res.content_type,
        res.attachment_mime_type,
        res.is_voice_note
      )
    );
    scroll_to_bottom(this.$chat_space_container);
  }

  render() {
    this.$wrapper.html(this.$chat_space);
    this.setup_events();

    scroll_to_bottom(this.$chat_space_container);
  }
}
