// 岗位分类 API：用于侧边栏导航。
import { apiClient } from "./client";

export interface JobCategory {
  name: string;
  count: number;
}

export interface CategoriesResponse {
  categories: JobCategory[];
}

export function getCategories(): Promise<CategoriesResponse> {
  return apiClient.get<CategoriesResponse>("/api/v1/sync/categories");
}
