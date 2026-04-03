import { ReactNode } from 'react';
import AdminSidebar from './AdminSidebar';

const AdminLayout = ({ children }: { children: ReactNode }) => (
  <div className="min-h-screen flex bg-background">
    <AdminSidebar />
    <main className="flex-1 p-6 overflow-auto">{children}</main>
  </div>
);

export default AdminLayout;
