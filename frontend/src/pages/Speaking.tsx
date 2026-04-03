import { useEffect } from 'react';
import { motion } from 'framer-motion';
import { Mic, Clock, MessageSquare, Zap, ArrowRight } from 'lucide-react';
import { Card, CardContent, CardDescription, CardTitle } from '@/components/ui/card';
import Layout from '@/components/Layout';
import { useNavigate } from 'react-router-dom';
import { useThemeContext } from '@/contexts/ThemeContext';

const parts = [
  { id: '1', title: 'Part 1', description: 'Introduction & Interview', time: '4-5 min', questions: '~12 questions about familiar topics', icon: MessageSquare },
  { id: '2', title: 'Part 2', description: 'Long Turn', time: '3-4 min', questions: 'Speak for 1-2 minutes on a topic card', icon: Mic },
  { id: '3', title: 'Part 3', description: 'Discussion', time: '4-5 min', questions: 'Abstract questions linked to Part 2 topic', icon: Zap },
  { id: 'all', title: 'Full Test', description: 'All Parts', time: '11-14 min', questions: 'Complete IELTS Speaking test simulation', icon: Mic },
];

const Speaking = () => {
  const navigate = useNavigate();
  const { setStudyMode } = useThemeContext();
  useEffect(() => { setStudyMode('speaking'); }, [setStudyMode]);

  return (
    <Layout>
      <div className="container mx-auto px-4 py-8 max-w-3xl relative">
        <div className="absolute w-80 h-80 bg-primary/5 rounded-full blur-3xl -top-20 -left-20 pointer-events-none animate-float" />

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="relative z-10">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-xl bg-primary/10">
              <Mic className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-foreground">Speaking Practice</h1>
              <p className="text-muted-foreground">Select a part to start your speaking test</p>
            </div>
          </div>

          <div className="grid gap-4 mt-8">
            {parts.map((part, i) => (
              <motion.div
                key={part.id}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.1, type: 'spring' }}
                whileHover={{ x: 6, transition: { duration: 0.15 } }}
                whileTap={{ scale: 0.98 }}
              >
                <Card
                  className="cursor-pointer hover:glow-sm transition-all border-border/50 hover:border-primary/40 group overflow-hidden relative"
                  onClick={() => navigate(`/speaking/test/${part.id}`)}
                >
                  <div className="absolute inset-0 bg-gradient-to-r from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                  <CardContent className="flex items-center gap-6 py-6 relative z-10">
                    <motion.div
                      whileHover={{ rotate: 5 }}
                      className="p-4 rounded-2xl bg-primary/10 group-hover:bg-primary/20 transition-colors"
                    >
                      <part.icon className="h-8 w-8 text-primary" />
                    </motion.div>
                    <div className="flex-1">
                      <CardTitle className="text-xl mb-1 group-hover:text-primary transition-colors">{part.title}</CardTitle>
                      <CardDescription className="font-medium">{part.description}</CardDescription>
                      <div className="flex items-center gap-3 mt-2">
                        <span className="flex items-center gap-1 text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                          <Clock className="h-3 w-3" /> {part.time}
                        </span>
                        <span className="text-xs text-muted-foreground">{part.questions}</span>
                      </div>
                    </div>
                    <ArrowRight className="h-5 w-5 text-muted-foreground opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </Layout>
  );
};

export default Speaking;
