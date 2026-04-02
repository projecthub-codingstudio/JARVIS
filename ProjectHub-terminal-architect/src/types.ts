export interface Message {
  id: string;
  role: 'operator' | 'architect';
  timestamp: string;
  content: string;
}

export interface Asset {
  id: string;
  type: 'pdf' | 'image' | 'docx' | 'hwp' | 'html';
  name: string;
  size?: string;
  status?: string;
  description?: string;
  matchPrecision?: string;
  imageUrl?: string;
  content?: string;
}

export interface UserProfile {
  uid: string;
  displayName: string;
  email: string;
  photoURL: string;
  role: 'admin' | 'user';
  createdAt: string;
  updatedAt: string;
}

export interface SystemLog {
  id: string;
  timestamp: string;
  type: 'info' | 'warning' | 'error';
  message: string;
  userId?: string;
}

export type ViewState = 'dashboard' | 'detail_report' | 'detail_image' | 'detail_code' | 'login' | 'profile' | 'admin';
