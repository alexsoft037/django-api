Feature: User authentication

  Scenario: User signs up with an email
    Given user registers with necessary data
      And server sends confirmation email
      When user clicks a verification url
       And user logs in
      Then user finishes registration

  Scenario: Admin logs in to admin panel
    Given admin user exists
      When admin logs in
      Then admin can manage website
