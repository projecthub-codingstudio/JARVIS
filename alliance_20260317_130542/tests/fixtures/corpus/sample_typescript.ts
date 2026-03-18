/**
 * REST API client for the TaskFlow project management service.
 * Handles authentication, request retries, and response parsing.
 */

interface TaskFlowConfig {
  baseUrl: string;
  apiKey: string;
  timeout?: number;
  maxRetries?: number;
}

interface Task {
  id: string;
  title: string;
  status: "todo" | "in_progress" | "review" | "done";
  assignee: string | null;
  priority: number;
  storyPoints: number;
  createdAt: string;
}

interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  hasNext: boolean;
}

class TaskFlowClient {
  private baseUrl: string;
  private apiKey: string;
  private timeout: number;
  private maxRetries: number;

  constructor(config: TaskFlowConfig) {
    this.baseUrl = config.baseUrl.replace(/\/$/, "");
    this.apiKey = config.apiKey;
    this.timeout = config.timeout ?? 30000;
    this.maxRetries = config.maxRetries ?? 3;
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown
  ): Promise<T> {
    const url = `${this.baseUrl}/api/v2${path}`;
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      try {
        const response = await fetch(url, {
          method,
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${this.apiKey}`,
            "X-Client-Version": "2.1.0",
          },
          body: body ? JSON.stringify(body) : undefined,
          signal: AbortSignal.timeout(this.timeout),
        });

        if (response.status === 429) {
          const retryAfter = parseInt(response.headers.get("Retry-After") ?? "5");
          await new Promise((r) => setTimeout(r, retryAfter * 1000));
          continue;
        }

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return (await response.json()) as T;
      } catch (error) {
        lastError = error as Error;
        if (attempt < this.maxRetries) {
          await new Promise((r) => setTimeout(r, 1000 * Math.pow(2, attempt)));
        }
      }
    }

    throw lastError;
  }

  async listTasks(
    page: number = 1,
    pageSize: number = 20,
    status?: Task["status"]
  ): Promise<PaginatedResponse<Task>> {
    const params = new URLSearchParams({ page: String(page), pageSize: String(pageSize) });
    if (status) params.set("status", status);
    return this.request<PaginatedResponse<Task>>("GET", `/tasks?${params}`);
  }

  async getTask(taskId: string): Promise<Task> {
    return this.request<Task>("GET", `/tasks/${taskId}`);
  }

  async createTask(task: Omit<Task, "id" | "createdAt">): Promise<Task> {
    return this.request<Task>("POST", "/tasks", task);
  }

  async updateTaskStatus(taskId: string, status: Task["status"]): Promise<Task> {
    return this.request<Task>("PATCH", `/tasks/${taskId}`, { status });
  }

  async deleteTask(taskId: string): Promise<void> {
    await this.request<void>("DELETE", `/tasks/${taskId}`);
  }

  async getSprintVelocity(sprintId: string): Promise<{ planned: number; completed: number }> {
    return this.request("GET", `/sprints/${sprintId}/velocity`);
  }
}

export { TaskFlowClient, TaskFlowConfig, Task, PaginatedResponse };
