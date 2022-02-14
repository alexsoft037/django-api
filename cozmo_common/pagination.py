from rest_framework.pagination import PageNumberPagination


class PageNumberTenPagination(PageNumberPagination):
    page_size = 10


class PageNumberFiftyPagination(PageNumberPagination):
    page_size = 100
