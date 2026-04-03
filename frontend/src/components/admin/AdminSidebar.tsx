import { useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  PenTool, Users, Bot, Mic, Shield, ChevronLeft,
  LayoutDashboard
} from 'lucide-react';
import { Button } from '@/components/ui/button';

const adminNavItems = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, path: '/admin' },
  { id: 'writing', label: 'Writing Topics', icon: PenTool, path: '/admin/writing-topics' },
  { id: 'users', label: 'User Management', icon: Users, path: '/admin/users' },
  { id: 'ai', label: 'AI Configuration', icon: Bot, path: '/admin/ai-config' },
  { id: 'speaking', label: 'Speaking Config', icon: Mic, path: '/admin/speaking-config' },
];

const AdminSidebar = () => {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <aside className="w-64 min-h-screen bg-card border-r border-border flex flex-col">
      <div className="p-4 border-b border-border">
        <div className="flex items-center gap-2">
          <Shield className="h-5 w-5 text-primary" />
          <span className="font-heading font-bold text-lg text-foreground">Admin Panel</span>
        </div>
        <p className="text-xs text-muted-foreground mt-1">Manage your IELTS platform</p>
      </div>

      <nav className="flex-1 p-3 space-y-1">
        {adminNavItems.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <button
              key={item.id}
              onClick={() => navigate(item.path)}
              className={`relative w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
              }`}
            >
              {isActive && (
                <motion.div
                  layoutId="adminActiveNav"
                  className="absolute inset-0 bg-primary rounded-lg"
                  transition={{ type: 'spring', bounce: 0.2, duration: 0.4 }}
                />
              )}
              <span className="relative z-10 flex items-center gap-3">
                <item.icon className="h-4 w-4" />
                {item.label}
              </span>
            </button>
          );
        })}
      </nav>

      <div className="p-3 border-t border-border">
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start gap-2 text-muted-foreground"
          onClick={() => navigate('/')}
        >
          <ChevronLeft className="h-4 w-4" />
          Back to App
        </Button>
      </div>
    </aside>
  );
};

export default AdminSidebar;
