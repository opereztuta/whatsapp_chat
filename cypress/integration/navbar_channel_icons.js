describe("Desk chat navbar controls", () => {
  const channelControls = [
    {
      wrapper: ".chat-navbar-icon",
      button: "#whatsapp-chat-navbar-button",
      icon: ".fa-whatsapp",
      panel: "#whatsapp-chat-panel",
    },
    {
      wrapper: ".messenger-navbar-icon",
      button: "#messenger-chat-navbar-button",
      icon: "svg",
      panel: "#messenger-chat-panel",
    },
    {
      wrapper: ".instagram-navbar-icon",
      button: "#instagram-chat-navbar-button",
      icon: ".fa-instagram",
      panel: "#instagram-chat-panel",
    },
  ];

  const parseColor = (color) => {
    const values = color.match(/[\d.]+/g).map(Number);
    return values.slice(0, 3);
  };

  const luminance = (color) => {
    const channels = parseColor(color).map((value) => {
      const normalized = value / 255;
      return normalized <= 0.04045
        ? normalized / 12.92
        : ((normalized + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
  };

  const contrastRatio = (first, second) => {
    const firstLuminance = luminance(first);
    const secondLuminance = luminance(second);
    return (
      (Math.max(firstLuminance, secondLuminance) + 0.05) /
      (Math.min(firstLuminance, secondLuminance) + 0.05)
    );
  };

  const installApiStubs = (capabilityOverrides = {}) => {
    cy.intercept("GET", "**/whatsapp_chat.api.config.settings*", {
      body: {
        message: {
          can_access_ui: true,
          can_access_whatsapp: true,
          can_access_messenger: true,
          can_access_instagram: true,
          enable_chat: true,
          is_admin: true,
          user: "Administrator",
          user_email: "administrator@example.com",
          user_settings: {},
          ...capabilityOverrides,
        },
      },
    });
    cy.intercept("GET", "**/whatsapp_chat.api.contacts.get*", {
      body: { message: [] },
    });
    cy.intercept("GET", "**/whatsapp_chat.api.messenger.get_contacts*", {
      body: { message: [] },
    });
    cy.intercept("POST", "**/frappe_instagram.api.ui.bootstrap*", {
      body: {
        message: {
          enabled: 1,
          can_manage: true,
          user: "Administrator",
          accounts: [],
          capabilities: {},
        },
      },
    });
    cy.intercept("GET", "**/frappe_instagram.api.ui.list_conversations*", {
      body: { message: { items: [], next_cursor: null, unread_count: 0 } },
    });
  };

  const expectAccessibleContrast = (theme) => {
    cy.document().then((document) => {
      document.documentElement.setAttribute("data-theme", theme);
    });
    cy.get("header.navbar").then(($navbar) => {
      const navbarColor = getComputedStyle($navbar[0]).backgroundColor;
      channelControls.forEach(({ button }) => {
        cy.get(button).then(($button) => {
          const styles = getComputedStyle($button[0]);
          expect(
            contrastRatio(styles.color, styles.backgroundColor),
            `${button} glyph-to-tile contrast in ${theme} theme`
          ).to.be.at.least(3);
          expect(
            contrastRatio(styles.backgroundColor, navbarColor),
            `${button} tile-to-navbar contrast in ${theme} theme`
          ).to.be.at.least(3);
          expect(styles.opacity).to.equal("1");
        });
      });
    });
  };

  beforeEach(() => {
    cy.login();
    installApiStubs();
    cy.visit("/app");
    cy.get(".chat-channel-navbar-button").should("have.length", 3);
  });

  it("renders recognizable, consistently sized channel controls", () => {
    channelControls.forEach(({ wrapper, button, icon, panel }) => {
      cy.get(wrapper).should("be.visible");
      cy.get(button)
        .should("have.attr", "type", "button")
        .and("have.attr", "aria-expanded", "false")
        .and("have.attr", "aria-controls", panel.slice(1))
        .then(($button) => {
          const bounds = $button[0].getBoundingClientRect();
          expect(bounds.width).to.equal(32);
          expect(bounds.height).to.equal(32);
        });
      cy.get(`${button} ${icon}`).should("exist");
    });
    cy.get("#messenger-chat-navbar-button svg").should(
      "not.have.attr",
      "style"
    );
    cy.get("#messenger-chat-navbar-button svg").should(
      "have.css",
      "fill",
      "rgb(255, 255, 255)"
    );
  });

  it("maintains non-text contrast in light and dark Desk themes", () => {
    expectAccessibleContrast("light");
    expectAccessibleContrast("dark");
  });

  it("opens and closes every panel from its keyboard-focusable button", () => {
    channelControls.forEach(({ button, panel }) => {
      cy.get(button).focus().should("be.focused").click();
      cy.get(button)
        .should("have.attr", "aria-expanded", "true")
        .and("have.css", "opacity", "1")
        .and("not.have.css", "box-shadow", "none");
      cy.get(panel).should("be.visible");
      cy.get(button).click();
      cy.get(button).should("have.attr", "aria-expanded", "false");
      cy.get(panel).should("not.be.visible");
    });
  });

  it("clears the open state when an outside click closes Instagram", () => {
    cy.get("#instagram-chat-navbar-button").click();
    cy.get("#instagram-chat-navbar-button").should(
      "have.attr",
      "aria-expanded",
      "true"
    );
    cy.get("body").trigger("mouseup");
    cy.get("#instagram-chat-navbar-button").should(
      "have.attr",
      "aria-expanded",
      "false"
    );
    cy.get("#instagram-chat-panel").should("not.be.visible");
  });

  it("renders empty and multi-digit unread badges without obscuring logos", () => {
    channelControls.forEach(({ button }) => {
      cy.get(`${button} .badge`).should("not.be.visible").invoke("text", "7");
      cy.get(`${button} .badge`).should("be.visible").invoke("text", "302");
      cy.get(`${button} .badge`).then(($badge) => {
        expect($badge[0].getBoundingClientRect().width).to.be.greaterThan(18);
      });
    });
  });

  it("keeps channel capability flags independent", () => {
    installApiStubs({ can_access_messenger: false });
    cy.reload();
    cy.get("#whatsapp-chat-navbar-button").should("be.visible");
    cy.get("#instagram-chat-navbar-button").should("be.visible");
    cy.get("#messenger-chat-navbar-button").should("not.exist");
  });

  it("keeps the three controls separate at a narrow Desk width", () => {
    cy.viewport(768, 900);
    cy.get(".chat-channel-navbar-button").then(($buttons) => {
      const bounds = [...$buttons].map((button) =>
        button.getBoundingClientRect()
      );
      bounds.forEach((current, index) => {
        bounds.slice(index + 1).forEach((next) => {
          const overlaps =
            current.left < next.right &&
            current.right > next.left &&
            current.top < next.bottom &&
            current.bottom > next.top;
          expect(overlaps).to.equal(false);
        });
      });
    });
  });
});
