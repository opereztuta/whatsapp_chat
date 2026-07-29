export function get_voice_recorder_html() {
  return `
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
  `;
}

export default class VoiceRecorder {
  constructor(opts) {
    this.$scope = opts.$scope;
    this.on_send = opts.on_send;
    this.get_error_message = opts.get_error_message;
    this.attach_selector = opts.attach_selector
      || '.open-attach-items,.messenger-open-attach';
    this.recorder = null;
    this.stream = null;
    this.chunks = [];
    this.mime_type = null;
    this.timer = null;
    this.started_at = null;
    this.should_send = false;
    this.sending = false;
  }

  bind() {
    this.$scope
      .find('.voice-record-button')
      .off('click.voice-recorder')
      .on('click.voice-recorder', () => this.start());
    this.$scope
      .find('.voice-stop-button')
      .off('click.voice-recorder')
      .on('click.voice-recorder', () => this.stop(true));
    this.$scope
      .find('.voice-cancel-button')
      .off('click.voice-recorder')
      .on('click.voice-recorder', () => this.stop(false));
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

  get_file_extension(mime_type) {
    const normalized = (mime_type || '').split(';')[0].toLowerCase();
    if (normalized === 'audio/mp4') return 'm4a';
    if (normalized === 'audio/webm') return 'webm';
    return 'ogg';
  }

  update_timer() {
    if (!this.started_at) return;
    const elapsed = Math.floor((Date.now() - this.started_at) / 1000);
    const minutes = Math.floor(elapsed / 60);
    const seconds = `${elapsed % 60}`.padStart(2, '0');
    this.$scope.find('.voice-recording-timer').text(`${minutes}:${seconds}`);
  }

  set_controls_disabled(disabled) {
    this.$scope.find('.type-message').prop('disabled', disabled);
    this.$scope.find(this.attach_selector).toggleClass('disabled', disabled);
    this.$scope.find('.message-send-button').toggleClass('disabled', disabled);
    this.$scope
      .find('.voice-record-button')
      .prop('disabled', disabled)
      .toggleClass('disabled', disabled);
  }

  set_recording_ui(is_recording) {
    this.set_controls_disabled(is_recording || this.sending);
    this.$scope.find('.voice-record-button').toggleClass('hidden', is_recording);
    this.$scope.find('.voice-recording-state').toggleClass('hidden', !is_recording);
  }

  cleanup_recording() {
    if (this.timer) clearInterval(this.timer);
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
    }
    this.recorder = null;
    this.stream = null;
    this.chunks = [];
    this.mime_type = null;
    this.timer = null;
    this.started_at = null;
    this.should_send = false;
    this.$scope.find('.voice-recording-timer').text('0:00');
    this.set_recording_ui(false);
  }

  async start() {
    if (this.recorder || this.sending) return;
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
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.chunks = [];
      this.mime_type = mime_type;
      this.should_send = false;
      this.recorder = new MediaRecorder(
        this.stream,
        mime_type ? { mimeType: mime_type } : {}
      );
      this.recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) this.chunks.push(event.data);
      };
      this.recorder.onstop = () => this.finish();
      this.recorder.onerror = () => {
        this.cleanup_recording();
        frappe.msgprint({
          title: __('Voice recording failed'),
          message: __('The browser could not continue recording audio.'),
          indicator: 'red',
        });
      };
      this.recorder.start();
      this.started_at = Date.now();
      this.update_timer();
      this.timer = setInterval(() => this.update_timer(), 1000);
      this.set_recording_ui(true);
    } catch (error) {
      this.cleanup_recording();
      frappe.msgprint({
        title: __('Microphone permission needed'),
        message: __('Allow microphone access to record a voice note.'),
        indicator: 'red',
      });
    }
  }

  stop(should_send) {
    if (!this.recorder) return;
    this.should_send = should_send;
    if (this.recorder.state !== 'inactive') {
      this.recorder.stop();
    } else {
      this.finish();
    }
  }

  async finish() {
    const should_send = this.should_send;
    const chunks = this.chunks;
    const mime_type = this.mime_type || (chunks[0] ? chunks[0].type : '');
    this.cleanup_recording();
    if (!should_send) return;
    if (!chunks.length) {
      frappe.msgprint({
        title: __('Empty voice note'),
        message: __('No audio was recorded.'),
        indicator: 'red',
      });
      return;
    }

    const blob = new Blob(chunks, { type: mime_type || 'audio/ogg' });
    const file = new File(
      [blob],
      `voice-note-${Date.now()}.${this.get_file_extension(blob.type || mime_type)}`,
      { type: blob.type || mime_type }
    );

    this.sending = true;
    this.set_controls_disabled(true);
    try {
      await this.on_send(file, file.type || mime_type);
    } catch (error) {
      const fallback = __('This voice note could not be sent.');
      frappe.msgprint({
        title: __('Could not send voice note'),
        message: this.get_error_message
          ? this.get_error_message(error, fallback)
          : (error.message || fallback),
        indicator: 'red',
      });
    } finally {
      this.sending = false;
      this.set_controls_disabled(false);
    }
  }

  destroy() {
    this.$scope.find('.voice-record-button').off('.voice-recorder');
    this.$scope.find('.voice-stop-button').off('.voice-recorder');
    this.$scope.find('.voice-cancel-button').off('.voice-recorder');
    if (this.recorder && this.recorder.state !== 'inactive') {
      this.should_send = false;
      this.recorder.onstop = null;
      this.recorder.stop();
    }
    this.cleanup_recording();
  }
}
