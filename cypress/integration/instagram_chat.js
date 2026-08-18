describe("Native Instagram Desk Chat", () => {
  const conversation = {
    name: "CONV-1",
    account: "Support",
    account_label: "@support",
    account_enabled: 1,
    account_health: "Active",
    igsid: "IGSID-1",
    username: "safe_user",
    full_name: "<img src=x onerror=alert(1)>",
    status: "Open",
    assigned_to: "",
    unread_count: 1,
    last_message_at: "2026-08-17 12:00:00",
    last_message_preview: "<script>unsafe()</script>",
    can_reply: 1,
    reply_window_expires_at: "2026-08-18 12:00:00",
  };

  beforeEach(() => {
    cy.login();
    cy.intercept("GET", "**/whatsapp_chat.api.config.settings*", {
      body: { message: { can_access_instagram: true } },
    });
    cy.intercept("POST", "**/frappe_instagram.api.ui.bootstrap*", {
      body: {
        message: {
          enabled: 1,
          can_manage: false,
          user: "agent@example.com",
          accounts: [{ name: "Support", label: "@support" }],
          capabilities: { text: true, image: true, audio: true, video: true },
        },
      },
    });
    cy.intercept("GET", "**/frappe_instagram.api.ui.list_conversations*", {
      body: { message: { items: [conversation], next_cursor: null } },
    });
    cy.intercept("POST", "**/frappe_instagram.api.ui.mark_read*", {
      body: { message: { conversation: "CONV-1", unread_count: 0 } },
    });
    cy.intercept("POST", "**/frappe_instagram.api.ui.claim_conversation*", {
      body: {
        message: { ...conversation, assigned_to: "agent@example.com" },
      },
    });
    cy.intercept("GET", "**/frappe_instagram.api.ui.list_messages*", {
      body: {
        message: {
          items: [
            {
              name: "IG-MSG-1",
              direction: "Incoming",
              message_type: "text",
              status: "received",
              message: "<img src=x onerror=alert(1)>",
              timestamp: "2026-08-17 12:00:00",
            },
          ],
          next_cursor: null,
        },
      },
    });
    cy.visit("/app");
  });

  it("shows a dedicated account-scoped inbox and escapes provider content", () => {
    cy.get(".instagram-navbar-icon").should("be.visible").click();
    cy.get(".instagram-account-badge").should("contain.text", "@support");
    cy.get(".instagram-room")
      .should("contain.text", "<script>unsafe()</script>")
      .click();
    cy.get(".instagram-message-bubble").should(
      "contain.text",
      "<img src=x onerror=alert(1)>",
    );
    cy.get(".instagram-message-bubble img").should("not.exist");
  });

  it("exposes the shared-queue and rich composer controls", () => {
    cy.get(".instagram-navbar-icon").click();
    cy.get(".instagram-room").click();
    cy.get(".instagram-claim").should("be.visible");
    cy.get(".instagram-quick").should("be.disabled");
    cy.get(".instagram-claim").click();
    cy.get(".instagram-quick").should("be.enabled");
    cy.get(".instagram-post").should("be.enabled");
    cy.get(".voice-record-button").should("be.enabled");
  });

  it("renders queued and failed outbound media with one safe inline reason", () => {
    cy.intercept("GET", "**/frappe_instagram.api.ui.list_messages*", {
      body: {
        message: {
          items: [
            {
              name: "IG-MSG-PENDING",
              direction: "Outgoing",
              message_type: "audio",
              status: "pending",
              is_voice_note: 1,
              media_url: "/api/method/signed-test-media",
              timestamp: "2026-08-17 12:01:00",
            },
            {
              name: "IG-MSG-FAILED",
              direction: "Outgoing",
              message_type: "audio",
              status: "failed",
              is_voice_note: 1,
              media_url: "/api/method/signed-test-media",
              failure_reason: "Meta could not fetch this voice note.",
              timestamp: "2026-08-17 12:02:00",
            },
          ],
          next_cursor: null,
        },
      },
    });

    cy.get(".instagram-navbar-icon").click();
    cy.get(".instagram-room").click();
    cy.get('[data-message-name="IG-MSG-PENDING"]')
      .should("contain.text", "Voice note")
      .and("contain.text", "pending");
    cy.get('[data-message-name="IG-MSG-FAILED"] .instagram-send-error')
      .should("have.length", 1)
      .and("contain.text", "Meta could not fetch this voice note.");
  });

  it("keeps the post picker bound to the conversation that opened it", () => {
    const first = { ...conversation, assigned_to: "agent@example.com" };
    const second = {
      ...conversation,
      name: "CONV-2",
      account: "Other",
      account_label: "@other",
      igsid: "IGSID-2",
      username: "other_user",
      assigned_to: "agent@example.com",
    };
    cy.intercept("GET", "**/frappe_instagram.api.ui.list_conversations*", {
      body: { message: { items: [first, second], next_cursor: null } },
    });
    cy.intercept("GET", "**/frappe_instagram.api.ui.list_owned_media*", {
      body: {
        message: {
          items: [
            {
              id: "MEDIA-1",
              caption: "Account A post",
              media_type: "IMAGE",
            },
          ],
          next_cursor: null,
        },
      },
    }).as("ownedMedia");
    cy.intercept("POST", "**/frappe_instagram.api.ui.send_media_share*", {
      body: { message: { name: "IG-MSG-SHARE" } },
    }).as("sendPost");
    cy.reload();

    cy.get(".instagram-navbar-icon").click();
    cy.get(".instagram-room").first().click();
    cy.get(".instagram-post").click();
    cy.wait("@ownedMedia").its("request.query.account").should("eq", "Support");

    // Simulate a selection change behind the modal. The post dialog must retain
    // the conversation/account pair with which its media was loaded.
    cy.get(".instagram-back").click({ force: true });
    cy.get(".instagram-room").eq(1).click({ force: true });
    cy.get(".instagram-post-card").click();
    cy.wait("@sendPost").then(({ request }) => {
      const body =
        typeof request.body === "string"
          ? Object.fromEntries(new URLSearchParams(request.body))
          : request.body;
      expect(body.conversation).to.equal("CONV-1");
      expect(body.media_id).to.equal("MEDIA-1");
      expect(body).not.to.have.property("account");
    });
  });
});
