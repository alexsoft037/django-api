def get_distance_str(distance_in_m, units="mi"):
    distance = round(int(distance_in_m) / 1609.34, ndigits=1)
    if distance < 0.5:
        distance_str = "less than half a"
    elif distance == 0.5:
        distance_str = "half"
    elif distance <= 1.0:
        distance_str = "less than a"
    else:
        distance_str = distance
    return f"{distance_str} {units}"
