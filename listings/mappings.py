def reverse_dict(d):
    ret = dict()
    for key in d.keys():
        inner = {x: key for x in d[key]}
        inner[key] = key
        ret.update(inner)
    return ret


features_syn_mapping = dict(
    laundry=["laundry in room", "washer", "dryer"],
    internet=["high speed internet", "internet", "internet access", "free wifi"],
    parking=["parking spaces"],
    car_rental=[],
    free_breakfast=[],
    room_service=[],
    cooling=["ac"],
    hot_tub=["heated pool", "pri hot tub", "private hot tub", "jacuzzi"],
    airport_shuttle=[],
    wheelchair=[],
    essentials=["towels", "towels provided"],
    kitchen=["full kitchen", "kitchenette"],
    ac=["air conditioning", "a.c.", "cooling"],
    heating=[],
    hair_dryer=[],
    hangers=[],
    iron=["iron & board", "clothes iron"],
    washer=["washing machine", "clothes washer"],
    dryer=["clothes dryer"],
    hot_water=[],
    tv=["television", "flat screen tv", "flat screen tv's", "tv's", "t.v.", "flat panel tv"],
    cable=["satellite"],
    fireplace=["furnace"],
    private_entrance=[],
    private_living_room=[],
    lock_on_bedroom_door=[],
    shampoo=[],
    bed_linens=["linens", "linens provided", "bed sheets"],
    extra_pillows_and_blankets=["extra bedding"],
    wireless_internet=["high speed internet", "internet", "internet access", "free wifi"],
    ethernet_connection=["high speed internet", "internet", "internet access"],
    pocket_wifi=[],
    laptop_friendly=[],
    # Kitchen
    microwave=[],
    coffee_maker=[],
    refrigerator=[],
    dishwasher=[],
    dishes_and_silverware=["dishes & utensils", "dishes", "silverware"],
    cooking_basics=[],
    oven=[],
    stove=["cooking range", "wood stove"],
    # Facility
    free_parking=[],
    street_parking=[],
    paid_parking=[],
    paid_parking_on_premises=[],
    ev_charger=[],
    gym=["fitness center", "fitness room", "firness room / equipment", "exercise room"],
    pool=["communal pool", "indoor pool", "community pool", "pool access", "private pool"],
    jacuzzi=["spa/jacuzzi", "hot tub", "heated pool", "pri hot tub", "private hot tub"],
    single_level_home=[],
    # Outdoor
    bbq_area=[
        "outdoor grill",
        "bbq",
        "barbeque",
        "grill",
        "outdoor bbq",
        "grill/bbq",
        "gas grill",
        "gas grill / bbq",
    ],
    patio_or_balcony=["deck", "deck / patio", "deck or balcony"],
    garden_or_backyard=["lawn", "garden", "lawn / garden", "yard"],
    # Special
    breakfast=[],
    beach_essentials=[],
    # Logistics
    luggage_dropoff_allowed=[],
    long_term_stays_allowed=[],
    cleaning_before_checkout=[],
    # Home Safety
    fire_extinguisher=[],
    carbon_monoxide_detector=[],
    smoke_detector=["smoke detectors"],
    first_aid_kit=[],
    # Location
    beachfront=[],
    lake_access=[],
    ski_in_ski_out=[
        "ski access",
        "ski-in",
        "ski-out",
        "ski-in/ski-out",
        "ski in/out",
        "ski in - ski out",
        "ski-in / ski-out",
    ],
    waterfront=[],
    # Family
    baby_bath=[],
    baby_monitor=[],
    babysitter_recommendations=["babysitter"],
    bathtub=[],
    changing_table=[],
    childrens_books_and_toys=["toys"],
    childrens_dinnerware=[],
    crib=[],
    fireplace_guards=[],
    game_console=["game room"],
    high_chair=[],
    outlet_covers=[],
    pack_n_play_travel_crib=[],
    room_darkening_shades=[],
    stair_gates=[],
    table_corner_guards=[],
    window_guards=[],
    # Accessibility Inside Home
    wide_hallway_clearance=[],
    # Accessibility Getting Home
    home_step_free_access=["single story"],
    elevator=["elevators"],
    path_to_entrance_lit_at_night=[],
    home_wide_doorway=[],
    flat_smooth_pathway_to_front_door=[],
    disabled_parking_spot=[],
    # Accessibility Bedroom
    bedroom_step_free_access=[],
    wide_clearance_to_bed=[],
    bedroom_wide_doorway=[],
    accessible_height_bed=[],
    electric_profiling_bed=[],
    # Accessibility Bathroom
    bathroom_step_free_access=[],
    grab_rails_in_shower=[],
    grab_rails_in_toilet=[],
    accessible_height_toilet=[],
    rollin_shower=[],
    shower_chair=[],
    bathroom_wide_doorway=[],
    tub_with_shower_bench=[],
    wide_clearance_to_shower_and_toilet=[],
    handheld_shower_head=[],
    # Accessibility Common Areas
    common_space_step_free_access=[],
    common_space_wide_doorway=[],
    # Accessibility Equipment
    mobile_hoist=[],
    pool_hoist=[],
    ceiling_hoist=[],
)

suitability_mapping = dict(
    elderly=["elderly friendly"],
    pets=["pets not allowed", "pets allowed", "pets considered", "pets permitted"],
    kids=["children welcome", "suitable for children"],
    large_groups=[],
    events=["events allowed", "events friendly"],
    smoking=[
        # "non smoking only",
        "smoking friendly",
        # "no smoking"
    ],
    handicap=[
        "handicap",
        "wheelchair accessible",
        # "wheelchair inaccessible",
        "handicap accessible",
        "wheelchair friendly",
    ],
    infants=["infants friendly"],
)

features_syn_rev = reverse_dict(features_syn_mapping)
suitability_rev = reverse_dict(suitability_mapping)
