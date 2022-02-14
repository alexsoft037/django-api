Feature: Dealing with reservations

  Scenario: User can create a new reservation
     Given Account with given email exists
     Given Account has right permissions
       And user is logged in
       And user has a property
      When user creates a new reservation
      Then user can see a new reservation listed
