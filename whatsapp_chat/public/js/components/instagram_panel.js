import { get_error_message, upload_chat_file } from "./chat_utils";
import VoiceRecorder, { get_voice_recorder_html } from "./voice_recorder";
import { instagram_call, instagram_request_id } from "./instagram_api";

function format_time(value) {
  if (!value) return "";
  return frappe.datetime.prettyDate(value);
}

function display_name(conversation) {
  return conversation.full_name || conversation.username || conversation.igsid;
}

export default class InstagramPanel {
  constructor(opts) {
    this.$wrapper = opts.$wrapper;
    this.config = opts.config;
    this.conversations = [];
    this.next_cursor = null;
    this.active = null;
    this.voice_recorder = null;
    this.filters = {
      status: "Open",
      assignment: "all",
      account: "",
      search: "",
    };
    this.setup_realtime();
    this.render_list();
  }

  async refresh_conversations(append = false) {
    try {
      const result = await instagram_call("list_conversations", {
        ...this.filters,
        cursor: append ? this.next_cursor : null,
      });
      this.conversations = append
        ? [...this.conversations, ...(result.items || [])]
        : result.items || [];
      this.next_cursor = result.next_cursor;
      this.total_unread = Number(result.unread_count || 0);
      this.render_rooms();
      this.update_badge();
    } catch (error) {
      this.show_error(error, __("Could not load Instagram conversations."));
    }
  }

  render_list() {
    if (this.voice_recorder) this.voice_recorder.destroy();
    this.active = null;
    this.$list = $(document.createElement("div")).addClass(
      "chat-list instagram-list",
    );
    const account_options = this.config.accounts
      .map(
        (account) =>
          `<option value='${frappe.utils.escape_html(
            account.name,
          )}'>${frappe.utils.escape_html(account.label)}</option>`,
      )
      .join("");
    this.$list.html(`
      <div class='chat-list-header'><h3>${__("Instagram Chats")}</h3></div>
      <div class='instagram-filters'>
        <input class='form-control instagram-search' type='search' placeholder='${__(
          "Search conversation",
        )}'>
        <div class='instagram-filter-row'>
          <select class='form-control instagram-account-filter'><option value=''>${__(
            "All accounts",
          )}</option>${account_options}</select>
          <select class='form-control instagram-status-filter'>
            <option>Open</option><option>Snoozed</option><option>Closed</option><option>All</option>
          </select>
          <select class='form-control instagram-assignment-filter'>
            <option value='all'>${__(
              "All visible",
            )}</option><option value='mine'>${__(
              "Mine",
            )}</option><option value='unassigned'>${__("Unassigned")}</option>
          </select>
        </div>
      </div>
      <div class='chat-rooms-container instagram-rooms'></div>
    `);
    this.$wrapper.html(this.$list);
    let search_timer;
    this.$list.find(".instagram-search").on("input", (event) => {
      clearTimeout(search_timer);
      search_timer = setTimeout(() => {
        this.filters.search = $(event.currentTarget).val().trim();
        this.refresh_conversations();
      }, 250);
    });
    this.$list.find(".instagram-account-filter").on("change", (event) => {
      this.filters.account = $(event.currentTarget).val();
      this.refresh_conversations();
    });
    this.$list.find(".instagram-status-filter").on("change", (event) => {
      this.filters.status = $(event.currentTarget).val();
      this.refresh_conversations();
    });
    this.$list.find(".instagram-assignment-filter").on("change", (event) => {
      this.filters.assignment = $(event.currentTarget).val();
      this.refresh_conversations();
    });
    this.$list.find(".instagram-rooms").on("scroll", (event) => {
      const element = event.currentTarget;
      if (
        this.next_cursor &&
        element.scrollTop + element.clientHeight >= element.scrollHeight - 30
      ) {
        const cursor = this.next_cursor;
        this.next_cursor = null;
        this.refresh_conversations(true).catch(() => {
          this.next_cursor = cursor;
        });
      }
    });
    this.refresh_conversations();
  }

  render_rooms() {
    const $container = this.$list && this.$list.find(".instagram-rooms");
    if (!$container || !$container.length) return;
    $container.empty();
    if (!this.conversations.length) {
      $container.append(
        $(document.createElement("div"))
          .addClass("instagram-empty")
          .text(__("No Instagram conversations found.")),
      );
      return;
    }
    this.conversations.forEach((conversation) => {
      const $room = $(document.createElement("div")).addClass(
        "chat-room instagram-room",
      );
      const $avatar = $(document.createElement("div")).addClass(
        "instagram-avatar",
      );
      if (conversation.profile_picture_url) {
        $avatar.append(
          $(document.createElement("img")).attr({
            src: conversation.profile_picture_url,
            alt: "",
          }),
        );
      } else {
        $avatar.text(
          (display_name(conversation) || "?").slice(0, 1).toUpperCase(),
        );
      }
      const $info = $(document.createElement("div")).addClass(
        "chat-profile-info",
      );
      const $name = $(document.createElement("div"))
        .addClass("chat-name")
        .text(display_name(conversation));
      if (conversation.is_verified)
        $name.append(
          $(document.createElement("span"))
            .addClass("instagram-verified")
            .text("✓"),
        );
      if (conversation.unread_count)
        $name.append(
          $(document.createElement("span"))
            .addClass("instagram-unread")
            .text(conversation.unread_count),
        );
      $info.append($name);
      $info.append(
        $(document.createElement("div"))
          .addClass("last-message")
          .text(conversation.last_message_preview || __("No messages yet")),
      );
      $info.append(
        $(document.createElement("span"))
          .addClass("instagram-account-badge")
          .text(conversation.account_label),
      );
      $room.append(
        $avatar,
        $info,
        $(document.createElement("div"))
          .addClass("chat-date")
          .text(format_time(conversation.last_message_at)),
      );
      $room.on("click", () => this.open_conversation(conversation));
      $container.append($room);
    });
  }

  async open_conversation(conversation) {
    this.active = conversation;
    await instagram_call(
      "mark_read",
      { conversation: conversation.name },
      "POST",
    );
    conversation.unread_count = 0;
    this.render_thread();
    await this.load_messages();
  }

  render_thread() {
    const conversation = this.active;
    this.$thread = $(document.createElement("div")).addClass(
      "chat-space instagram-space",
    );
    const assignment_action = this.config.can_manage
      ? `<button class='btn btn-xs instagram-assign'>${__("Assign")}</button>`
      : conversation.assigned_to
        ? `<button class='btn btn-xs instagram-release'>${__("Release")}</button>`
        : `<button class='btn btn-xs btn-primary instagram-claim'>${__(
            "Claim",
          )}</button>`;
    this.$thread.html(`
      <div class='chat-header instagram-header'>
        <span class='chat-back-button instagram-back'>${frappe.utils.icon(
          "left",
        )}</span>
        <div class='chat-profile-info'>
          <div class='chat-profile-name'></div>
          <div class='instagram-header-meta'></div>
        </div>
        <div class='instagram-thread-actions'>${assignment_action}
          <select class='form-control instagram-thread-status'><option>Open</option><option>Snoozed</option><option>Closed</option></select>
        </div>
      </div>
      <div class='chat-space-container instagram-messages'><button class='btn btn-xs instagram-older hidden'>${__(
        "Load older",
      )}</button></div>
      <div class='instagram-policy'></div>
      <div class='chat-space-actions instagram-actions'>
        <div class='instagram-rich-actions'>
          <button class='btn btn-xs instagram-heart' title='${__(
            "Send heart",
          )}'>♥</button>
          <button class='btn btn-xs instagram-quick'>${__(
            "Quick replies",
          )}</button>
          <button class='btn btn-xs instagram-post'>${__("Share post")}</button>
        </div>
        <div class='messenger-message-composer'>
          <span class='messenger-open-attach instagram-attach' title='${__(
            "Attach media",
          )}'>${frappe.utils.icon("attachment", "lg")}</span>
          <input type='file' class='instagram-file-uploader' accept='image/*,audio/*,video/mp4,video/quicktime' style='display:none'>
          <input class='form-control type-message instagram-message-input' type='text' placeholder='${__(
            "Type message",
          )}'>
          ${get_voice_recorder_html()}
          <span class='message-send-button instagram-send'>${frappe.utils.icon(
            "send",
            "sm",
          )}</span>
        </div>
      </div>
    `);
    this.$thread.find(".chat-profile-name").text(display_name(conversation));
    this.$thread
      .find(".instagram-header-meta")
      .text(
        `${conversation.account_label} · ${
          conversation.assigned_to || __("Unassigned")
        }`,
      );
    this.$thread.find(".instagram-thread-status").val(conversation.status);
    this.$wrapper.html(this.$thread);
    this.bind_thread_events();
    this.update_composer_state();
  }

  async load_messages(before = null) {
    // A realtime event can land between open_conversation() setting this.active
    // and render_thread() building this.$thread, so neither is safe to assume.
    const conversation = this.active;
    if (!conversation || !this.$thread) return;
    const $container = this.$thread.find(".instagram-messages");
    const previous_height =
      before && $container.length ? $container[0].scrollHeight : 0;
    const previous_scroll =
      before && $container.length ? $container.scrollTop() : 0;
    try {
      const result = await instagram_call("list_messages", {
        conversation: conversation.name,
        before,
      });
      // The user may have switched threads or gone back to the list while the
      // request was in flight; those messages no longer belong on screen.
      if (this.active !== conversation || !this.$thread) return;
      this.message_cursor = result.next_cursor;
      this.messages = before
        ? [...(result.items || []), ...(this.messages || [])]
        : result.items || [];
      this.render_messages({
        preserve: Boolean(before),
        previous_height,
        previous_scroll,
      });
    } catch (error) {
      if (
        this.active &&
        ["PermissionError", "AuthenticationError"].includes(error.exc_type)
      ) {
        this.active.user_has_access = false;
        this.update_composer_state();
      }
      this.show_error(error, __("Could not load Instagram messages."));
    }
  }

  render_messages(scroll = {}) {
    const $container = this.$thread.find(".instagram-messages").empty();
    if (this.message_cursor) {
      $container.append(
        $(document.createElement("button"))
          .addClass("btn btn-xs instagram-older")
          .text(__("Load older")),
      );
    }
    const groups = [];
    (this.messages || []).forEach((message) => {
      const key =
        message.message_id && Number(message.attachment_count || 0) > 1
          ? `${message.direction}:${message.message_id}`
          : null;
      const previous = groups[groups.length - 1];
      if (key && previous && previous.key === key) {
        previous.messages.push(message);
      } else {
        groups.push({ key, messages: [message] });
      }
    });
    groups.forEach((group) => {
      group.messages.sort(
        (left, right) =>
          Number(left.attachment_index || 0) -
          Number(right.attachment_index || 0),
      );
      if (group.messages.length === 1) {
        $container.append(this.render_message(group.messages[0]));
        return;
      }
      const $group = $(document.createElement("div"))
        .addClass("instagram-attachment-group")
        .attr("data-provider-message-id", group.messages[0].message_id);
      group.messages.forEach((message) =>
        $group.append(this.render_message(message)),
      );
      $container.append($group);
    });
    $container
      .off("click.older")
      .on("click.older", ".instagram-older", () =>
        this.load_messages(this.message_cursor),
      );
    if (scroll.preserve) {
      $container.scrollTop(
        $container[0].scrollHeight -
          scroll.previous_height +
          scroll.previous_scroll,
      );
    } else {
      $container.scrollTop($container[0].scrollHeight);
    }
  }

  render_message(message) {
    const outgoing = message.direction === "Outgoing";
    const $row = $(document.createElement("div"))
      .addClass(outgoing ? "recipient-message" : "sender-message")
      .attr("data-message-name", message.name);
    const $bubble = $(document.createElement("div")).addClass(
      "message-bubble instagram-message-bubble",
    );
    if (message.status === "deleted" || message.message_type === "deleted") {
      $bubble.addClass("text-muted").text(__("Message deleted"));
    } else if (message.message_type === "like_heart") {
      $bubble.addClass("instagram-heart-message").text("♥");
    } else if (message.message_type === "postback") {
      $bubble.append(
        $(document.createElement("strong")).text(
          message.postback_title || __("Postback"),
        ),
      );
      if (message.postback_payload)
        $bubble.append(
          $(document.createElement("div")).text(message.postback_payload),
        );
    } else if (message.message_type === "referral") {
      $bubble.text(
        `${__("Referral")}: ${
          message.referral_ref || message.referral_source || ""
        }`,
      );
    } else if (message.attachment_status === "Pending") {
      $bubble.addClass("text-muted").text(__("Attachment processing…"));
    } else if (["Failed", "Skipped"].includes(message.attachment_status)) {
      $bubble
        .addClass("text-muted")
        .text(message.attachment_error || __("Attachment unavailable"));
    } else if (
      message.media_url &&
      ["image", "story_mention", "story_reply", "share", "reel"].includes(
        message.message_type,
      )
    ) {
      $bubble.append(
        $(document.createElement("img"))
          .addClass("chat-image")
          .attr({ src: message.media_url, alt: message.attachment_name || "" }),
      );
      if (message.message)
        $bubble.append($(document.createElement("div")).text(message.message));
    } else if (message.media_url && message.message_type === "video") {
      $bubble.append(
        $(document.createElement("video")).addClass("chat-video").attr({
          src: message.media_url,
          controls: true,
          preload: "metadata",
        }),
      );
    } else if (message.media_url && message.message_type === "audio") {
      $bubble.append(
        $(document.createElement("div"))
          .addClass("chat-audio-label")
          .text(message.is_voice_note ? __("Voice note") : __("Audio")),
      );
      $bubble.append(
        $(document.createElement("audio")).attr({
          src: message.media_url,
          controls: true,
          preload: "metadata",
        }),
      );
    } else if (message.media_url && message.message_type === "file") {
      $bubble.append(
        $(document.createElement("a"))
          .attr({
            href: message.media_url,
            target: "_blank",
            rel: "noopener noreferrer",
          })
          .text(message.attachment_name || __("Download file")),
      );
    } else if (message.shared_media_permalink) {
      $bubble.append(
        $(document.createElement("a"))
          .attr({
            href: message.shared_media_permalink,
            target: "_blank",
            rel: "noopener noreferrer",
          })
          .text(__("View shared Instagram post")),
      );
    } else {
      const fallback =
        message.message ||
        (message.message_type === "unsupported"
          ? __("Unsupported Instagram message")
          : `[${message.message_type}]`);
      $bubble.text(fallback);
    }
    if (message.reply_to_message_id)
      $bubble.prepend(
        $(document.createElement("div"))
          .addClass("instagram-reply-context")
          .text(__("Reply to an earlier message")),
      );
    if (message.reply_to_story_id)
      $bubble.prepend(
        $(document.createElement("div"))
          .addClass("instagram-reply-context")
          .text(__("Story reply")),
      );
    if (message.quick_reply_payload)
      $bubble.append(
        $(document.createElement("div"))
          .addClass("instagram-event-label")
          .text(`${__("Quick reply")}: ${message.quick_reply_payload}`),
      );
    if (message.quick_replies && message.quick_replies.length) {
      const $choices = $(document.createElement("div")).addClass(
        "instagram-quick-reply-options",
      );
      message.quick_replies.forEach((choice) => {
        $choices.append(
          $(document.createElement("span")).text(
            choice.title || choice.content_type,
          ),
        );
      });
      $bubble.append($choices);
    }
    if (message.reaction_emoji)
      $bubble.append(
        $(document.createElement("span"))
          .addClass("instagram-reaction")
          .text(
            message.reaction_emoji === "love" ? "♥" : message.reaction_emoji,
          ),
      );
    if (outgoing && message.status === "failed") {
      $bubble.append(
        $(document.createElement("div"))
          .addClass("instagram-send-error text-muted")
          .text(
            message.failure_reason ||
              __("This Instagram attachment could not be sent."),
          ),
      );
    }
    if (!outgoing && message.message_id && message.status !== "deleted") {
      $bubble
        .attr("title", __("Click to react"))
        .on("dblclick", () => this.toggle_reaction(message));
    }
    const status = outgoing ? ` · ${message.status || ""}` : "";
    $row.append(
      $bubble,
      $(document.createElement("div"))
        .addClass("message-time")
        .text(`${format_time(message.timestamp)}${status}`),
    );
    return $row;
  }

  bind_thread_events() {
    this.$thread.find(".instagram-back").on("click", () => this.render_list());
    this.$thread
      .find(".instagram-claim")
      .on("click", () => this.change_conversation("claim_conversation"));
    this.$thread
      .find(".instagram-release")
      .on("click", () => this.change_conversation("release_conversation"));
    this.$thread
      .find(".instagram-assign")
      .on("click", () => this.show_assign_dialog());
    this.$thread.find(".instagram-thread-status").on("change", (event) =>
      this.change_conversation("set_conversation_status", {
        status: $(event.currentTarget).val(),
      }),
    );
    this.$thread.find(".instagram-send").on("click", () => this.send_text());
    this.$thread.find(".instagram-message-input").on("keydown", (event) => {
      if (event.key === "Enter") this.send_text();
    });
    this.$thread
      .find(".instagram-attach")
      .on("click", () => this.$thread.find(".instagram-file-uploader").click());
    this.$thread.find(".instagram-file-uploader").on("change", (event) => {
      const file = event.currentTarget.files && event.currentTarget.files[0];
      if (file) this.send_file(file, false);
      event.currentTarget.value = "";
    });
    this.$thread
      .find(".instagram-heart")
      .on("click", () => this.send_special("send_like_heart"));
    this.$thread
      .find(".instagram-quick")
      .on("click", () => this.show_quick_reply_dialog());
    this.$thread
      .find(".instagram-post")
      .on("click", () => this.show_post_picker());
    this.voice_recorder = new VoiceRecorder({
      $scope: this.$thread,
      get_error_message,
      attach_selector: ".instagram-attach",
      on_send: (file) => this.send_file(file, true),
    });
    this.voice_recorder.bind();
  }

  update_composer_state() {
    const requires_claim =
      !this.config.can_manage && this.active.assigned_to !== this.config.user;
    const blocked =
      this.active.user_has_access === false ||
      requires_claim ||
      this.active.status !== "Open" ||
      !this.active.can_reply ||
      this.active.is_opted_out ||
      !this.active.account_enabled ||
      !["Active", "Warning"].includes(this.active.account_health);
    this.$thread
      .find(".instagram-policy")
      .text(
        blocked
          ? this.active.user_has_access === false
            ? __("You no longer have access to this conversation.")
            : requires_claim
              ? __("Claim this conversation before replying.")
              : this.active.is_opted_out
                ? __("This profile is marked Do Not Contact.")
                : __(
                    "The Instagram 24-hour reply window is closed or the account is unavailable.",
                  )
          : `${__("Reply window ends")} ${format_time(
              this.active.reply_window_expires_at,
            )}`,
      );
    this.$thread
      .find(".instagram-actions input, .instagram-actions button")
      .prop("disabled", blocked);
    this.$thread
      .find(
        ".instagram-actions .message-send-button, .instagram-actions .instagram-attach",
      )
      .toggleClass("disabled", blocked);
  }

  async change_conversation(method, extra = {}) {
    try {
      this.active = await instagram_call(
        method,
        { conversation: this.active.name, ...extra },
        "POST",
      );
      this.render_thread();
      await this.load_messages();
    } catch (error) {
      this.show_error(error, __("Could not update the conversation."));
    }
  }

  show_assign_dialog() {
    const dialog = new frappe.ui.Dialog({
      title: __("Assign Instagram conversation"),
      fields: [
        {
          fieldname: "user",
          fieldtype: "Link",
          options: "User",
          label: __("User"),
          default: this.active.assigned_to || "",
          description: __(
            "Leave blank to return this conversation to the shared queue.",
          ),
        },
      ],
      primary_action_label: __("Assign"),
      primary_action: async (values) => {
        try {
          this.active = await instagram_call(
            "assign_conversation",
            {
              conversation: this.active.name,
              user: values.user || "",
            },
            "POST",
          );
          dialog.hide();
          this.render_thread();
          await this.load_messages();
        } catch (error) {
          this.show_error(error, __("Could not assign the conversation."));
        }
      },
    });
    dialog.show();
  }

  async send_text() {
    const $input = this.$thread.find(".instagram-message-input");
    const text = ($input.val() || "").trim();
    if (!text) return;
    $input.val("");
    try {
      await instagram_call(
        "send_text",
        {
          conversation: this.active.name,
          text,
          request_id: instagram_request_id(),
        },
        "POST",
      );
      await this.load_messages();
    } catch (error) {
      $input.val(text);
      this.show_error(error, __("Could not send the Instagram message."));
    }
  }

  async send_file(file, is_voice_note) {
    const mime = (file.type || "").toLowerCase();
    const type =
      is_voice_note || mime.startsWith("audio/")
        ? "audio"
        : mime.startsWith("video/")
          ? "video"
          : "image";
    try {
      // Instagram rejects oversized media anyway, so fail here rather than
      // after pushing the whole body up to the server.
      const limit = ((this.config.limits || {}).media || {})[type];
      if (limit && file.size > limit) {
        throw new Error(
          __("This {0} is larger than Instagram's {1} MB limit.", [
            type,
            Math.floor(limit / (1024 * 1024)),
          ]),
        );
      }
      const uploaded = await upload_chat_file(
        file,
        "Instagram Conversation",
        this.active.name,
        true,
      );
      await instagram_call(
        "send_attachment",
        {
          conversation: this.active.name,
          attachment_type: type,
          file: uploaded.name || uploaded.file_url,
          is_voice_note: is_voice_note ? 1 : 0,
          request_id: instagram_request_id(),
        },
        "POST",
      );
      await this.load_messages();
    } catch (error) {
      // VoiceRecorder owns its validation/enqueue dialog. Showing one here as
      // well produced two stacked errors for the same failed recording.
      if (!is_voice_note)
        this.show_error(error, __("Could not send the Instagram attachment."));
      throw error;
    }
  }

  async send_special(method) {
    try {
      await instagram_call(
        method,
        { conversation: this.active.name, request_id: instagram_request_id() },
        "POST",
      );
      await this.load_messages();
    } catch (error) {
      this.show_error(error, __("Could not send this Instagram message."));
    }
  }

  show_quick_reply_dialog() {
    const dialog = new frappe.ui.Dialog({
      title: __("Send quick replies"),
      fields: [
        {
          fieldname: "prompt",
          fieldtype: "Small Text",
          label: __("Prompt"),
          reqd: 1,
        },
        {
          fieldname: "choices",
          fieldtype: "Table",
          label: __("Choices"),
          reqd: 1,
          cannot_add_rows: false,
          fields: [
            {
              fieldname: "content_type",
              fieldtype: "Select",
              options: "text\nuser_email\nuser_phone_number",
              default: "text",
              in_list_view: 1,
              label: __("Type"),
            },
            {
              fieldname: "title",
              fieldtype: "Data",
              in_list_view: 1,
              label: __("Title"),
            },
            {
              fieldname: "payload",
              fieldtype: "Data",
              in_list_view: 1,
              label: __("Payload"),
            },
          ],
        },
      ],
      primary_action_label: __("Send"),
      primary_action: async (values) => {
        try {
          await instagram_call(
            "send_quick_replies",
            {
              conversation: this.active.name,
              prompt: values.prompt,
              quick_replies: JSON.stringify(values.choices || []),
              request_id: instagram_request_id(),
            },
            "POST",
          );
          dialog.hide();
          await this.load_messages();
        } catch (error) {
          this.show_error(error, __("Could not send quick replies."));
        }
      },
    });
    dialog.show();
  }

  async show_post_picker() {
    // Freeze both values for the lifetime of this dialog. The server still
    // derives the sender from the conversation, but this prevents a later UI
    // selection from pairing account A's picker results with conversation B.
    const conversation = this.active.name;
    const account = this.active.account;
    const dialog = new frappe.ui.Dialog({
      title: __("Share an Instagram post"),
      fields: [{ fieldname: "posts", fieldtype: "HTML" }],
    });
    dialog.show();
    const $posts = dialog.fields_dict.posts.$wrapper
      .addClass("instagram-post-picker")
      .text(__("Loading posts…"));
    try {
      const result = await instagram_call("list_owned_media", {
        account,
      });
      $posts.empty();
      (result.items || []).forEach((post) => {
        const $post = $(document.createElement("button")).addClass(
          "instagram-post-card",
        );
        if (post.thumbnail_url)
          $post.append(
            $(document.createElement("img")).attr({
              src: post.thumbnail_url,
              alt: "",
            }),
          );
        $post.append(
          $(document.createElement("span")).text(
            post.caption || post.media_type || __("Instagram post"),
          ),
        );
        $post.on("click", async () => {
          try {
            await instagram_call(
              "send_media_share",
              {
                conversation,
                media_id: post.id,
                request_id: instagram_request_id(),
              },
              "POST",
            );
            dialog.hide();
            await this.load_messages();
          } catch (error) {
            this.show_error(error, __("Could not share the Instagram post."));
          }
        });
        $posts.append($post);
      });
      if (!(result.items || []).length)
        $posts.text(__("No account-owned posts were returned by Instagram."));
    } catch (error) {
      $posts.text(
        get_error_message(error, __("Could not load Instagram posts.")),
      );
    }
  }

  async toggle_reaction(message) {
    try {
      await instagram_call(
        message.reaction_emoji ? "unreact" : "react",
        { conversation: this.active.name, message_id: message.message_id },
        "POST",
      );
      await this.load_messages();
    } catch (error) {
      this.show_error(error, __("Could not update the reaction."));
    }
  }

  setup_realtime() {
    frappe.realtime.on("instagram_chat_update", (event) => {
      if (this.active && event.conversation === this.active.name)
        this.load_messages();
      if (
        event.change === "failed" &&
        this.active &&
        event.conversation === this.active.name
      ) {
        frappe.show_alert({
          message: __("Instagram media could not be sent."),
          indicator: "red",
        });
      }
      this.refresh_conversations();
    });
    frappe.realtime.on("connect", () => {
      if (!this.$wrapper.is(":visible")) return;
      if (this.active) this.load_messages();
      this.refresh_conversations();
    });
    this.refresh_timer = setInterval(() => {
      if (this.$wrapper.is(":visible")) {
        if (this.active) this.load_messages();
        else this.refresh_conversations();
      }
    }, 60000);
  }

  update_badge() {
    const unread = Number(this.total_unread || 0);
    $("#instagram-notification-count").text(unread || "");
  }

  show_error(error, fallback) {
    frappe.msgprint({
      title: __("Instagram Chat"),
      message: get_error_message(error, fallback),
      indicator: "red",
    });
  }
}
