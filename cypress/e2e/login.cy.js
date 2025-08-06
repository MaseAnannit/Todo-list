describe('Login Page', () => {
  it('should load the login page', () => {
    cy.visit('/login');
    cy.contains('Login').should('be.visible');
  });

  it('should show an error on invalid credentials', () => {
    cy.visit('/login');
    cy.get('input[name="username"]').type('wronguser');
    cy.get('input[name="password"]').type('wrongpass');
    cy.get('button[type="submit"]').click();
    cy.contains('Invalid username or password'); 
  });

  it('should redirect on successful login', () => {
    cy.visit('/login');
    cy.get('input[name="username"]').type('admin');
    cy.get('input[name="password"]').type('password123');
    cy.get('button[type="submit"]').click();
    cy.url().should('include', '/todos');
  });
});