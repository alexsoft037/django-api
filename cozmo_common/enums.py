from enum import Enum


class ChoicesMixin:
    @property
    def pretty_name(self):
        return self.name.replace("_", " ")

    @classmethod
    def choices(cls):
        return tuple((field.value, field.pretty_name) for field in cls)


class RegularChoicesMixin(ChoicesMixin, Enum):
    """
    Subclassed from ChoicesMixin, this mixin overrides the choices field to
    map value to name instead of value to pretty name
    """
    @classmethod
    def choices(cls):
        return tuple((field.value, field.name) for field in cls)


class RegularValuesChoicesMixin(ChoicesMixin, Enum):
    """
    Subclassed from ChoicesMixin, this mixin overrides the choices field to
    map value to name instead of value to pretty name
    """
    @classmethod
    def choices(cls):
        return tuple((field.value, field.value) for field in cls)


class ChoicesEnum(ChoicesMixin, Enum):
    pass


class IntChoicesEnum(int, ChoicesMixin, Enum):
    pass


class RegularIntChoicesEnum(int, RegularChoicesMixin, Enum):
    """
    Like IntChoicesEnum, but using the RegularChoicesMixin which
    uses field name instead of pretty name
    """
    pass


class StrChoicesEnum(str, ChoicesMixin, Enum):
    pass
