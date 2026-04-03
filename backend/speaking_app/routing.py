from django.urls import path

from speaking_app.consumers import SpeakingTestConsumer

websocket_urlpatterns = [
    path("ws/speaking/test", SpeakingTestConsumer.as_asgi()),
]