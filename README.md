<div align="center">
  <h1>WhatsApp Chat</h1>
  <p>A real-time chat interface for WhatsApp Cloud API integration with Frappe</p>
</div>

![WhatsApp Chat Interface](https://github.com/shridarpatil/whatsapp_chat/assets/11792643/197d1d68-7ff7-48f5-a96c-221d1c6cb8db)

## Overview

WhatsApp Chat provides a WhatsApp-like chat interface directly within Frappe
Desk, enabling your team to send and receive WhatsApp, Messenger, and Instagram
messages without leaving the ERP system.

## Features

- **Real-time Messaging** - Send and receive WhatsApp messages with instant updates via Socket.IO
- **Chat Interface** - Familiar WhatsApp-like UI integrated into Frappe Desk
- **Contact Management** - Automatic contact creation from incoming messages
- **Media Support** - Send and receive images, documents, audio, and video on WhatsApp and Messenger; Instagram supports images and video
- **Private Meta Uploads** - Messenger and Instagram files are stored privately and uploaded directly to Meta without requiring public crawler access
- **Auto Read Receipts** - Automatically send read receipts to WhatsApp when viewing messages (based on WhatsApp Account settings)
- **Sound Notifications** - Audio alerts for new messages
- **Multi-user Support** - Assign contacts to specific users for follow-up

## Supported Media Types

| Type | Formats |
|------|---------|
| **Images** | PNG, JPEG, GIF, WebP, AVIF, SVG |
| **Documents** | PDF, Word, Excel, PowerPoint |
| **Audio** | AAC, MP4, MPEG, AMR, OGG |
| **Video** | MP4, 3GP |

## Prerequisites

- Frappe Framework >= 12.0.0
- [frappe_whatsapp](https://github.com/shridarpatil/frappe_whatsapp) app (required)
- WhatsApp Business Account configured in frappe_whatsapp

## Installation

```bash
# Install the app
bench get-app https://github.com/shridarpatil/whatsapp_chat
bench --site your-site install-app whatsapp_chat

# Build assets
bench build --app whatsapp_chat
```

## Usage

### Accessing the Chat

After installation, a chat bubble appears in Frappe Desk. Click it to open the chat interface.

### Receiving Messages

When a customer sends a WhatsApp message:
1. A new contact is automatically created (if not exists)
2. The message appears in the chat list
3. Sound notification plays (if enabled)
4. Real-time update via Socket.IO

### Sending Messages

> **Note:** Due to WhatsApp policy, you can only send direct messages to users who have messaged you first within the last 24 hours. For initiating conversations, use WhatsApp Templates via frappe_whatsapp.

1. Click on a contact from the chat list
2. Type your message or attach media
3. Press Send

### Contact Assignment

Assign contacts to specific users:
1. Open the WhatsApp Contact document
2. Set the **Email** field to the assigned user's email
3. Only that user will receive real-time notifications for that contact

## DocTypes

| DocType | Purpose |
|---------|---------|
| **WhatsApp Contact** | Stores contact information and last message |

## API Reference

### Get Messages

```python
from whatsapp_chat.api.message import get_all

messages = get_all(room="contact_name", user_no="919876543210")
```

### Send Message

```python
from whatsapp_chat.api.message import send

# Text message
send(content="Hello!", user="Administrator", room="contact", user_no="919876543210")

# With attachment
send(content="/files/document.pdf", user="Administrator", room="contact", user_no="919876543210", attachment=True)
```

### Mark as Read

```python
from whatsapp_chat.api.message import mark_as_read

mark_as_read(room="contact_name")
```

## Configuration

### Sound Settings

The app includes notification sounds:
- `chat-notification` - New message alert
- `chat-message-send` - Message sent confirmation
- `chat-message-receive` - Message received alert

## Related Apps

| App | Description |
|-----|-------------|
| [frappe_whatsapp](https://github.com/shridarpatil/frappe_whatsapp) | Core WhatsApp Cloud API integration (required) |
| [frappe_whatsapp_chatbot](https://github.com/shridarpatil/frappe_whatsapp_chatbot) | Automated chatbot with flows, keywords, and AI |

## Troubleshooting

### Messages Not Appearing in Real-time

1. Check Socket.IO is running: `bench doctor`
2. Verify the contact has an assigned email
3. Check browser console for WebSocket errors

### Cannot Send Messages

1. Ensure the contact messaged you within 24 hours
2. Verify WhatsApp Account token is valid
3. Check Error Log for API errors

### Media Not Sending

1. Verify file format is supported
2. Check file size limits (WhatsApp limits apply)
3. Ensure file URL is accessible

## License

MIT License

## Author

Shridhar Patil (shridharpatil2792@gmail.com)
