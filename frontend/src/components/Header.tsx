import { useNavigate, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Sun, Moon, Settings, PenTool, Mic, User, Sparkles, LayoutDashboard, LogOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useThemeContext } from '@/contexts/ThemeContext';
import { getCurrentUser, isAuthenticated, logoutRemote } from '@/lib/auth';

const Header = () => {
  const { studyMode, setStudyMode, theme, toggleTheme } = useThemeContext();
  const navigate = useNavigate();
  const location = useLocation();
  const authed = isAuthenticated();
  const user = getCurrentUser();

  const tabs = [
    { id: 'dashboard' as const, label: 'Dashboard', icon: LayoutDashboard, path: '/' },
    { id: 'writing' as const, label: 'Writing', icon: PenTool, path: '/writing' },
    { id: 'speaking' as const, label: 'Speaking', icon: Mic, path: '/speaking' },
  ];

  const isAuthPage = location.pathname === '/auth';
  if (isAuthPage) return null;

  return (
    <header className="sticky top-0 z-50 bg-card/70 backdrop-blur-xl border-b border-border/50">
      <div className="container mx-auto flex items-center justify-between h-16 px-4">
        <button onClick={() => navigate('/')} className="flex items-center gap-2 text-xl font-bold font-heading text-foreground hover:text-primary transition-colors group">
          <Sparkles className="h-5 w-5 text-primary group-hover:animate-wiggle" />
          IELTS Mastery
        </button>

        <div className="flex items-center gap-1 bg-muted/80 backdrop-blur-sm rounded-xl p-1 border border-border/50">
          {tabs.map(tab => {
            const isActive = location.pathname === tab.path || (tab.id !== 'dashboard' && studyMode === tab.id && location.pathname.startsWith(tab.path));
            return (
              <button
                key={tab.id}
                onClick={() => {
                  if (tab.id === 'writing' || tab.id === 'speaking') setStudyMode(tab.id);
                  navigate(tab.path);
                }}
                className={`relative px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive ? 'text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {isActive && (
                  <motion.div
                    layoutId="activeTab"
                    className="absolute inset-0 bg-primary rounded-lg glow-sm"
                    transition={{ type: 'spring', bounce: 0.2, duration: 0.5 }}
                  />
                )}
                <span className="relative z-10 flex items-center gap-2">
                  <tab.icon className="h-4 w-4" />
                  {tab.label}
                </span>
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" onClick={toggleTheme} className="hover:bg-primary/10">
            {theme === 'light' ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
          </Button>
          <Button variant="ghost" size="icon" onClick={() => navigate('/settings')} className="hover:bg-primary/10">
            <Settings className="h-4 w-4" />
          </Button>
          {authed ? (
            <Button variant="ghost" size="icon" onClick={async () => { await logoutRemote(); navigate('/auth'); }} className="hover:bg-primary/10" title={`Logout ${user?.username || ''}`}>
              <LogOut className="h-4 w-4" />
            </Button>
          ) : (
            <Button variant="ghost" size="icon" onClick={() => navigate('/auth')} className="hover:bg-primary/10">
              <User className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </header>
  );
};

export default Header;
