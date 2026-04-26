from django.urls import path
from . import views

urlpatterns = [
    path('merchants/', views.MerchantListView.as_view(), name='merchant-list'),
    path('merchants/<int:merchant_id>/balance/', views.MerchantBalanceView.as_view(), name='merchant-balance'),
    path('merchants/<int:merchant_id>/payouts/', views.PayoutListView.as_view(), name='merchant-payouts'),
    path('payouts/', views.PayoutCreateView.as_view(), name='payout-create'),
    path('payouts/<int:payout_id>/', views.PayoutDetailView.as_view(), name='payout-detail'),
]
