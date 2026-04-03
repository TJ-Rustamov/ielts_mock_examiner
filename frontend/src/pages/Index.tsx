import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { PenTool, Mic, Sparkles, Zap, BarChart3, Shield, ArrowRight, Star } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Layout from '@/components/Layout';

const floatingShapes = [
  { size: 'w-64 h-64', color: 'bg-primary/5', position: 'top-20 -left-32', delay: 0 },
  { size: 'w-48 h-48', color: 'bg-primary/8', position: 'top-40 right-10', delay: 2 },
  { size: 'w-32 h-32', color: 'bg-accent/30', position: 'bottom-32 left-20', delay: 4 },
  { size: 'w-56 h-56', color: 'bg-secondary/40', position: 'bottom-10 -right-20', delay: 1 },
];

const features = [
  { icon: Sparkles, title: 'AI-Powered Feedback', desc: 'Get instant, detailed evaluations on every response' },
  { icon: Zap, title: 'Band 7-9 Upgrades', desc: 'See exactly how to rewrite for higher scores' },
  { icon: BarChart3, title: 'Progress Tracking', desc: 'Visual charts showing your improvement over time' },
  { icon: Shield, title: 'Exam Simulation', desc: 'Practice under real IELTS conditions with timers' },
];

const stats = [
  { value: '10K+', label: 'Students' },
  { value: '95%', label: 'Improved' },
  { value: '7.5', label: 'Avg. Score' },
  { value: '50K+', label: 'Tests Taken' },
];

const Index = () => {
  const navigate = useNavigate();

  return (
    <Layout>
      {/* Hero */}
      <section className="relative overflow-hidden min-h-[85vh] flex items-center">
        {floatingShapes.map((s, i) => (
          <div
            key={i}
            className={`absolute ${s.size} ${s.color} rounded-full blur-3xl ${s.position} ${i % 2 === 0 ? 'animate-float' : 'animate-float-reverse'}`}
            style={{ animationDelay: `${s.delay}s` }}
          />
        ))}

        <div className="container mx-auto px-4 relative z-10">
          <div className="max-w-3xl mx-auto text-center">
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7 }}
            >
              <div className="inline-flex items-center gap-2 bg-primary/10 text-primary px-4 py-1.5 rounded-full text-sm font-medium mb-6">
                <Star className="h-4 w-4 animate-wiggle" />
                The #1 IELTS Prep Platform
              </div>
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.1 }}
              className="text-5xl md:text-7xl font-bold font-heading text-foreground mb-6 leading-tight"
            >
              Master IELTS{' '}
              <span className="gradient-text">Speaking</span>{' '}
              &{' '}
              <span className="gradient-text">Writing</span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.2 }}
              className="text-xl text-muted-foreground mb-10 max-w-xl mx-auto"
            >
              Get AI-powered feedback, band score predictions, and personalized improvements to achieve your target score.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.3 }}
              className="flex flex-col sm:flex-row items-center justify-center gap-4"
            >
              <Button
                size="lg"
                className="gap-2 text-base px-8 h-12 glow"
                onClick={() => navigate('/writing')}
              >
                <PenTool className="h-5 w-5" /> Start Writing
                <ArrowRight className="h-4 w-4" />
              </Button>
              <Button
                size="lg"
                variant="outline"
                className="gap-2 text-base px-8 h-12"
                onClick={() => navigate('/speaking')}
              >
                <Mic className="h-5 w-5" /> Start Speaking
              </Button>
            </motion.div>
          </div>

          {/* Stats bar */}
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.5 }}
            className="mt-20 glass-card rounded-2xl p-6 max-w-2xl mx-auto"
          >
            <div className="grid grid-cols-4 divide-x divide-border">
              {stats.map((s, i) => (
                <motion.div
                  key={s.label}
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.7 + i * 0.1, type: 'spring' }}
                  className="text-center px-4"
                >
                  <p className="text-2xl md:text-3xl font-bold text-primary">{s.value}</p>
                  <p className="text-xs text-muted-foreground mt-1">{s.label}</p>
                </motion.div>
              ))}
            </div>
          </motion.div>
        </div>
      </section>

      {/* Features */}
      <section className="py-24 relative">
        <div className="container mx-auto px-4">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center mb-16"
          >
            <h2 className="text-3xl md:text-4xl font-bold font-heading text-foreground mb-4">
              Everything you need to <span className="gradient-text">ace IELTS</span>
            </h2>
            <p className="text-muted-foreground text-lg max-w-md mx-auto">
              Our AI analyzes your responses and gives you actionable feedback in seconds.
            </p>
          </motion.div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            {features.map((f, i) => (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                whileHover={{ y: -8, transition: { duration: 0.2 } }}
                className="group"
              >
                <div className="glass-card rounded-2xl p-6 h-full transition-all duration-300 group-hover:glow group-hover:border-primary/30">
                  <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-primary/20 transition-colors">
                    <f.icon className="h-6 w-6 text-primary" />
                  </div>
                  <h3 className="font-heading font-semibold text-foreground text-lg mb-2">{f.title}</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">{f.desc}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-24 relative overflow-hidden">
        <div className="absolute inset-0 bg-primary/5 rounded-3xl" />
        <div className="absolute w-72 h-72 bg-primary/10 rounded-full blur-3xl -top-20 -right-20 animate-float" />
        <div className="container mx-auto px-4 relative z-10 text-center">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
          >
            <h2 className="text-3xl md:text-4xl font-bold font-heading text-foreground mb-4">
              Ready to boost your score?
            </h2>
            <p className="text-lg text-muted-foreground mb-8 max-w-md mx-auto">
              Join thousands of students who improved their IELTS scores with AI-powered practice.
            </p>
            <Button size="lg" className="gap-2 text-base px-10 h-12 glow" onClick={() => navigate('/auth')}>
              Get Started Free <ArrowRight className="h-4 w-4" />
            </Button>
          </motion.div>
        </div>
      </section>
    </Layout>
  );
};

export default Index;
