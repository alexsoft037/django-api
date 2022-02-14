Feature: Property management

  Scenario: User creates property
     Given Account with given email exists 
       And user is logged in
      When user create a new property
      Then property is saved in a database

  Scenario: User adds a new property image
     Given Account with given email exists
       And user is logged in
       And user has a property
      When user sends a new property image
      Then property image is uploaded to a CDN

  Scenario: User bulk creates new rooms
     Given Account with given email exists
       And user is logged in
       And user has a property
      When user sends a list of new rooms
      Then new rooms are bulk create

  Scenario: User adds a new property image
     Given Account with given email exists
       And user is logged in
       And user has a property with images
      When user changes properties images order
      Then new properties images order is used

  Scenario: User gets whole data after updating property
     Given Account with given email exists
       And user is logged in
       And user has a property
      When user updates property data
      Then responses gives data of a whole property

  Scenario: User can see only his properties
     Given Account with given email exists
       And user is logged in
       And another user owns a property
      When user lists all properties
      Then user can see only owned properties

  Scenario: User can see basic properites' data
     Given Account with given email exists
       And user is logged in
       And user has a property
      When user lists all properties basic data
      Then user can see simplified response
