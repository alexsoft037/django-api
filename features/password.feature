Feature: Password reset

  Scenario: User forgets the password
     Given Account with given email exists 
       And user requests password reset
      When user clicks the password reset link
       And user provides a new password
      Then the new password is set

  Scenario: User provides wrong email
     Given Account with given email does not exist
       And user requests password reset
      Then the email is not sent
