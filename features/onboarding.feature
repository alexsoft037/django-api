Feature: Complete onboarding

  Scenario: User completes onboarding
     Given Account with given email exists
       And user is logged in
      When user submits onboarding data
      Then plan is sucessfully selected

  Scenario: User tries to use onboarding again
     Given Account with given email exists
       And user is logged in
       And user already had onboarding
      When user submits onboarding data
      Then plan is not updated
