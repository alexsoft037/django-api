from collections import OrderedDict, namedtuple


Category = namedtuple("Category", ["filter", "name", "icon"])


class Mapper:
    categories = OrderedDict(
        museums=Category(filter="museums", name="museums", icon="account-balance"),
        restaurants=Category(filter="restaurants", name="restaurants", icon="restaurant"),
        outdoor=Category(filter="fishing,hiking", name="outdoor activities", icon="sunny"),
        for_kids=Category(
            filter="amusementparks,kids_activities", name="kids friendly", icon="child-care"
        ),
        groceries=Category(filter="grocery", name="shopping/groceries", icon="cart"),
        nightlife=Category(filter="nightlife", name="bar/night life", icon="bar"),
        landmarks=Category(filter="landmarks", name="landmarks", icon="landmarks"),
        entertainment=Category(filter="entertainment", name="entertainment", icon="ticket"),
    )

    others = Category(filter="others", name="others", icon="others")

    @classmethod
    def get_all_categories(cls):
        all_categories = cls.categories.copy()
        all_categories.update({"others": cls.others})
        return all_categories
