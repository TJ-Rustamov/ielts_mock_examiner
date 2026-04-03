import { useState } from 'react';
import { motion } from 'framer-motion';
import { User, Trash2, Settings2, Shield, Server, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import Layout from '@/components/Layout';
import ProfileAvatar from '@/components/ProfileAvatar';
import { apiUrl, getBackendBaseUrl, setBackendBaseUrl } from '@/lib/backend';

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.08 } },
};
const item = {
  hidden: { opacity: 0, y: 15 },
  show: { opacity: 1, y: 0 },
};

const Settings = () => {
  const [selectedAvatar, setSelectedAvatar] = useState('??');
  const [showAvatarPicker, setShowAvatarPicker] = useState(false);
  const [backendUrl, setBackendUrl] = useState(getBackendBaseUrl());
  const [healthStatus, setHealthStatus] = useState<string | null>(null);

  const saveBackendUrl = () => {
    setBackendBaseUrl(backendUrl);
    setHealthStatus('Saved backend URL.');
  };

  const testBackend = async () => {
    try {
      const response = await fetch(apiUrl('/api/health'));
      if (!response.ok) throw new Error('Health check failed');
      setHealthStatus('Connected to backend.');
    } catch {
      setHealthStatus('Could not connect. Check backend URL and server status.');
    }
  };

  return (
    <Layout>
      <div className="container mx-auto px-4 py-8 max-w-2xl relative">
        <div className="absolute w-72 h-72 bg-primary/5 rounded-full blur-3xl -top-20 -right-20 pointer-events-none" />

        <motion.div variants={container} initial="hidden" animate="show" className="relative z-10">
          <motion.div variants={item} className="flex items-center gap-3 mb-8">
            <div className="p-2 rounded-xl bg-primary/10">
              <Settings2 className="h-6 w-6 text-primary" />
            </div>
            <h1 className="text-3xl font-bold text-foreground">Settings</h1>
          </motion.div>

          <motion.div variants={item}>
            <Card className="mb-6 overflow-hidden group hover:glow-sm transition-shadow">
              <CardHeader>
                <CardTitle>Profile Picture</CardTitle>
                <CardDescription>Choose an avatar or upload a custom picture</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-4">
                  <motion.div
                    whileHover={{ scale: 1.1, rotate: 5 }}
                    whileTap={{ scale: 0.95 }}
                    className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center text-4xl cursor-pointer hover:bg-primary/20 transition-colors glow-sm"
                    onClick={() => setShowAvatarPicker(!showAvatarPicker)}
                  >
                    {selectedAvatar}
                  </motion.div>
                  <Button variant="outline" onClick={() => setShowAvatarPicker(!showAvatarPicker)}>
                    Change Avatar
                  </Button>
                </div>
                {showAvatarPicker && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
                    <ProfileAvatar selected={selectedAvatar} onSelect={(a) => { setSelectedAvatar(a); setShowAvatarPicker(false); }} />
                  </motion.div>
                )}
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={item}>
            <Card className="mb-6 hover:glow-sm transition-shadow">
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><Server className="h-5 w-5 text-primary" /> Backend URL</CardTitle>
                <CardDescription>Set your backend host (example: http://localhost:8000)</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <Input value={backendUrl} onChange={(e) => setBackendUrl(e.target.value)} placeholder="http://localhost:8000" />
                <div className="flex gap-2">
                  <Button className="gap-2 glow-sm" onClick={saveBackendUrl}><Save className="h-4 w-4" /> Save</Button>
                  <Button variant="outline" onClick={testBackend}>Test Connection</Button>
                </div>
                {healthStatus && <p className="text-sm text-muted-foreground">{healthStatus}</p>}
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={item}>
            <Card className="mb-6 hover:glow-sm transition-shadow">
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><User className="h-5 w-5 text-primary" /> Username</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Input placeholder="New username" />
                <Button className="glow-sm">Update Username</Button>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={item}>
            <Card className="mb-6 hover:glow-sm transition-shadow">
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><Shield className="h-5 w-5 text-primary" /> Change Password</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Input type="password" placeholder="Current password" />
                <Input type="password" placeholder="New password" />
                <Input type="password" placeholder="Confirm new password" />
                <Button className="glow-sm">Update Password</Button>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={item}>
            <Card className="border-destructive/30 overflow-hidden relative group">
              <div className="absolute inset-0 bg-gradient-to-br from-destructive/5 to-transparent pointer-events-none" />
              <CardHeader className="relative z-10">
                <CardTitle className="flex items-center gap-2 text-destructive"><Trash2 className="h-5 w-5" /> Danger Zone</CardTitle>
                <CardDescription>Permanently delete your account and all data</CardDescription>
              </CardHeader>
              <CardContent className="relative z-10">
                <Button variant="destructive">Delete Account</Button>
              </CardContent>
            </Card>
          </motion.div>
        </motion.div>
      </div>
    </Layout>
  );
};

export default Settings;