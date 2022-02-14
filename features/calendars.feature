Feature: Calendars

  Scenario: User adds external calendar
     Given Account with given email exists
       And user is logged in
       And user has a property
      When user sees a calendar preview
      When user imports a calendar
      Then user sees imported calendar details

  Scenario: User exports calendar
     Given Account with given email exists
       And user has a property
       And Cozmo calendar exists
      When anonymous user visits calendar page
      Then anonymous user recieves iCal file
