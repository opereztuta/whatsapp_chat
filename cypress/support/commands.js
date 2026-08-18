Cypress.Commands.add("login", (email = "Administrator", password = "admin") => {
  return cy.session([email, password], () => {
    cy.request({
      method: "POST",
      url: "/api/method/login",
      body: { usr: email, pwd: password },
    })
      .its("status")
      .should("eq", 200);
  });
});
