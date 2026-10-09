// 支付 API：封装 /api/v1/payments/* 端点调用（验证版本）。
import { apiClient } from "./client";

export interface ProductInfo {
  code: string;
  name: string;
  price_cents: number;
  duration_days: number | null;
  lifetime: boolean;
}

export interface CreateOrderResponse {
  order_id: string;
  product_code: string;
  amount_cents: number;
  pay_url: string;
  status: string;
}

export interface OrderStatusResponse {
  order_id: string;
  status: string;
  product_code: string;
  amount_cents: number;
  paid_at: string | null;
  delivered_at: string | null;
}

export interface EntitlementResponse {
  type: string | null;
  active: boolean;
  expires_at: string | null;
  source_order_id: string | null;
}

// 与后端 PRODUCTS 一致（前端展示用）
export const PRODUCTS: ProductInfo[] = [
  {
    code: "trial_monthly",
    name: "月度试用",
    price_cents: 990,
    duration_days: 30,
    lifetime: false,
  },
  {
    code: "lifetime",
    name: "永久买断",
    price_cents: 9900,
    duration_days: null,
    lifetime: true,
  },
];

export const paymentsApi = {
  createOrder(product_code: string): Promise<CreateOrderResponse> {
    return apiClient.post<CreateOrderResponse>(
      "/api/v1/payments/create-order",
      { product_code },
    );
  },

  getOrderStatus(order_id: string): Promise<OrderStatusResponse> {
    return apiClient.get<OrderStatusResponse>(
      `/api/v1/payments/orders/${order_id}`,
    );
  },

  getEntitlement(): Promise<EntitlementResponse> {
    return apiClient.get<EntitlementResponse>("/api/v1/payments/entitlements");
  },

  /** 验证用：模拟支付宝异步通知服务端。真实接入时此方法删除。 */
  simulateNotify(order_id: string): Promise<{ msg: string; order_id: string; status: string }> {
    return apiClient.post<{ msg: string; order_id: string; status: string }>(
      `/api/v1/payments/test/simulate-notify?order_id=${encodeURIComponent(order_id)}`,
    );
  },
};
