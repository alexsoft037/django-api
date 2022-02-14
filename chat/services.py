import logging

from services.dialogflow import DialogFlowService
from chat.handlers import (
    AmenitiesHandler,
    CancellationHandler,
    DiscountHandler,
    DistanceHandler,
    EarlyBagDropoffHandler,
    EarlyCheckInHandler,
    LateCheckOutHandler,
    PetsHandler,
    RecommendationHandler,
    RefundHandler,
    SimpleResponseHandler,
    WifiHandler,
)
from chat.intents import Intent

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, message):
        self.engine = DialogFlowService()
        self.message = message
        self.settings = message.conversation.reservation.prop.organization.settings.chat_settings
        self.intent = None
        self.confidence = None
        self.parameters = None

    def get_intent_handler(self, intent):
        handler = {
            Intent.RECOMMENDATIONS.value: RecommendationHandler,
            Intent.DISTANCE.value: DistanceHandler,
            Intent.DISCOUNT.value: DiscountHandler,
            Intent.REFUND.value: RefundHandler,
            Intent.EARLY_BAG_DROPOFF.value: EarlyBagDropoffHandler,
            Intent.EARLY_CHECKIN.value: EarlyCheckInHandler,
            Intent.AMENITIES.value: AmenitiesHandler,
            Intent.WIFI.value: WifiHandler,
            Intent.PETS.value: PetsHandler,
            Intent.LATE_CHECK_OUT.value: LateCheckOutHandler,
            Intent.CANCELLATION.value: CancellationHandler,
        }.get(intent, SimpleResponseHandler)
        logger.debug(f"Got intent handler {handler}")
        return handler

    def get_message(self):
        intent, confidence, parameters = self.engine.detect_intent(self.message.text)
        self.intent = intent
        self.confidence = confidence
        self.parameters = parameters
        handler = self.get_intent_handler(intent)
        if handler:
            result = handler(message=self.message, intent=self.intent, parameters=self.parameters)
            return result.execute()
        return ""
