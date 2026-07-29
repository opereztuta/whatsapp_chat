import moment from 'moment';

function get_time(time) {
  let current_time;
  if (time) {
    current_time = moment(time);
  } else {
    current_time = moment();
  }
  return current_time.format('h:mm A');
}

function get_date_from_now(dateObj, type) {
  const sameDay = type === 'space' ? '[Today]' : 'h:mm A';
  const elseDay = type === 'space' ? 'MMM D, YYYY' : 'DD/MM/YYYY';
  const result = moment(dateObj).calendar(null, {
    sameDay: sameDay,
    lastDay: '[Yesterday]',
    lastWeek: elseDay,
    sameElse: elseDay,
  });
  return result;
}

function is_date_change(dateObj, prevObj) {
  const curDate = moment(dateObj).format('DD/MM/YYYY');
  const prevDate = moment(prevObj).format('DD/MM/YYYY');
  return curDate !== prevDate;
}

function scroll_to_bottom($element) {
  $element.animate(
    {
      scrollTop: $element[0].scrollHeight,
    },
    300
  );
}

function is_image(filename) {
  const allowedExtensions = /(\.jpg|\.jpeg|\.png|\.gif|\.webp)$/i;
  if (!allowedExtensions.exec(filename)) {
    return false;
  }
  return true;
}

function upload_chat_file(file_obj, doctype, docname, is_private = false) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.addEventListener('error', () => {
      reject(new Error(__('Internal Server Error')));
    });
    xhr.onreadystatechange = () => {
      if (xhr.readyState !== XMLHttpRequest.DONE) return;
      if (xhr.status === 200) {
        try {
          const response = JSON.parse(xhr.responseText);
          if (response.message && response.message.doctype === 'File') {
            resolve(response.message);
            return;
          }
        } catch (error) {
          // Fall through to the normalized upload error.
        }
        reject(new Error(__('File upload failed!')));
        return;
      }
      try {
        const error = JSON.parse(xhr.responseText);
        const messages = JSON.parse(error._server_messages);
        const first = JSON.parse(messages[0]);
        reject(new Error(__(first.message)));
      } catch (error) {
        reject(new Error(__('File upload failed!')));
      }
    };

    xhr.open('POST', '/api/method/upload_file', true);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.setRequestHeader('X-Frappe-CSRF-Token', frappe.csrf_token);
    const form_data = new FormData();
    form_data.append('file', file_obj, file_obj.name);
    form_data.append('is_private', is_private ? 1 : 0);
    form_data.append('doctype', doctype);
    form_data.append('docname', docname);
    form_data.append('optimize', 1);
    xhr.send(form_data);
  });
}

async function get_rooms() {
  const res = await frappe.call({
    type: 'GET',
    method: 'whatsapp_chat.api.contacts.get',
    args: {},
  });
  return await res.message;
}

async function get_messages(room) {
  const res = await frappe.call({
    method: 'whatsapp_chat.api.message.get_all',
    args: { room },
  });
  return await res.message;
}

function get_error_message(error, fallback) {
  if (error && error._server_messages) {
    try {
      const messages = JSON.parse(error._server_messages);
      if (messages.length) {
        const first = JSON.parse(messages[0]);
        if (first.message) {
          return first.message;
        }
      }
    } catch (e) {
      // fall through to other shapes
    }
  }

  if (error && error.message) {
    return error.message;
  }

  return fallback;
}

async function send_message(content, room, attachment, mime_type, content_type) {
  const res = await frappe.call({
    method: 'whatsapp_chat.api.message.send',
    args: {
      room,
      content,
      attachment: attachment || null,
      mime_type: mime_type || null,
      content_type: content_type || null,
    },
  });
  return res.message;
}

async function send_voice_note(room, attachment, mime_type) {
  const res = await frappe.call({
    method: 'whatsapp_chat.api.message.send_voice_note',
    args: {
      room,
      attachment,
      mime_type: mime_type || null,
    },
  });
  return res.message;
}

async function get_call_state(room) {
  const res = await frappe.call({
    method: 'whatsapp_chat.api.message.get_call_state',
    args: { room },
  });
  return res.message;
}

async function start_whatsapp_call(room) {
  const res = await frappe.call({
    method: 'whatsapp_chat.api.message.start_call',
    args: { room },
  });
  return res.message;
}

async function request_call_permission(room) {
  const res = await frappe.call({
    method: 'whatsapp_chat.api.message.request_call_permission',
    args: { room },
  });
  return res.message;
}

async function get_settings() {
  const res = await frappe.call({
    type: 'GET',
    method: 'whatsapp_chat.api.config.settings',
    args: {},
  });
  return await res.message;
}

async function mark_message_read(room) {
  try {
    await frappe.call({
      method: 'whatsapp_chat.api.message.mark_as_read',
      args: {
        room: room,
      },
    });
  } catch (error) {
    //pass
  }
}

function set_messenger_notification_count(type) {
  const current_count = frappe.MessengerChat.settings.unread_count;
  if (type === 'increment') {
    $('#messenger-notification-count').text(current_count + 1);
    frappe.MessengerChat.settings.unread_count += 1;
  } else {
    const next = current_count - 1;
    $('#messenger-notification-count').text(next <= 0 ? '' : next);
    frappe.MessengerChat.settings.unread_count = Math.max(0, next);
  }
}

async function send_messenger_message(room, content, attachment, mime_type) {
  const res = await frappe.call({
    method: 'whatsapp_chat.api.messenger.send_message',
    args: {
      room,
      content,
      attachment: attachment || null,
      mime_type: mime_type || null,
    },
  });
  return res.message;
}

async function send_messenger_voice_note(room, attachment, mime_type) {
  const res = await frappe.call({
    method: 'whatsapp_chat.api.messenger.send_voice_note',
    args: {
      room,
      attachment,
      mime_type: mime_type || null,
    },
  });
  return res.message;
}

async function get_messenger_rooms() {
  const res = await frappe.call({
    type: 'GET',
    method: 'whatsapp_chat.api.messenger.get_contacts',
    args: {},
  });
  return res.message;
}

async function get_messenger_messages(room) {
  const res = await frappe.call({
    method: 'whatsapp_chat.api.messenger.get_all_messages',
    args: { room },
  });
  return res.message;
}

async function create_private_room(contact_name, mobile_no, email) {
  await frappe.call({
    method: 'whatsapp_chat.api.contacts.create',
    args: {
      contact_name: contact_name,
      mobile_no: mobile_no,
      email: email
    },
  });
}

function get_avatar_html(room_type, user_email, room_name) {
  let avatar_html;
  if (room_type === 'Direct' && 'desk' in frappe) {
    avatar_html = frappe.avatar(user_email, 'avatar-medium');
  } else {
    avatar_html = frappe.get_avatar('avatar-medium', room_name);
  }
  return avatar_html;
}

function set_notification_count(type) {
  const current_count = frappe.Chat.settings.unread_count;
  if (type === 'increment') {
    $('#chat-notification-count').text(current_count + 1);
    frappe.Chat.settings.unread_count += 1;
  } else {
    if (current_count - 1 === 0) {
      $('#chat-notification-count').text('');
    } else {
      $('#chat-notification-count').text(current_count - 1);
    }
    frappe.Chat.settings.unread_count -= 1;
  }
}

export {
  get_time,
  scroll_to_bottom,
  get_rooms,
  get_messages,
  get_settings,
  send_message,
  send_voice_note,
  get_call_state,
  start_whatsapp_call,
  request_call_permission,
  get_date_from_now,
  is_date_change,
  mark_message_read,
  is_image,
  upload_chat_file,
  create_private_room,
  get_avatar_html,
  set_notification_count,
  get_error_message,
  get_messenger_rooms,
  get_messenger_messages,
  send_messenger_message,
  send_messenger_voice_note,
  set_messenger_notification_count,
};
