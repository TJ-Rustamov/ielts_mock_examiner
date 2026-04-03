import { motion } from 'framer-motion';
import { Check, Star, Sparkles, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import Layout from '@/components/Layout';

const plans = [
  {
    name: 'Free',
    price: '$0',
    period: 'forever',
    icon: Star,
    features: ['5 writing evaluations/month', '5 speaking tests/month', 'Basic feedback', 'Band score estimates'],
  },
  {
    name: 'Pro',
    price: '$19',
    period: '/month',
    icon: Zap,
    features: ['Unlimited evaluations', 'Detailed sentence analysis', 'Band 7-9 improvements', 'Audio synthesis', 'Priority processing', 'Progress analytics'],
    popular: true,
  },
  {
    name: 'Premium',
    price: '$39',
    period: '/month',
    icon: Sparkles,
    features: ['Everything in Pro', '1-on-1 expert review', 'Custom study plans', 'Mock test simulations', 'Vocabulary builder', 'Priority support'],
  },
];

const Pricing = () => (
  <Layout>
    <div className="container mx-auto px-4 py-16 relative">
      <div className="absolute w-96 h-96 bg-primary/5 rounded-full blur-3xl -top-40 left-1/2 -translate-x-1/2 pointer-events-none" />

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-16 relative z-10">
        <div className="inline-flex items-center gap-2 bg-primary/10 text-primary px-4 py-1.5 rounded-full text-sm font-medium mb-4">
          <Sparkles className="h-4 w-4" /> Simple Pricing
        </div>
        <h1 className="text-4xl md:text-5xl font-bold text-foreground mb-4 font-heading">
          Choose your <span className="gradient-text">plan</span>
        </h1>
        <p className="text-xl text-muted-foreground max-w-md mx-auto">Pick the plan that fits your IELTS preparation needs</p>
      </motion.div>

      <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto relative z-10">
        {plans.map((plan, i) => (
          <motion.div
            key={plan.name}
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.12, type: 'spring' }}
            whileHover={{ y: -8, transition: { duration: 0.2 } }}
          >
            <Card className={`relative h-full flex flex-col overflow-hidden transition-shadow ${
              plan.popular ? 'border-primary glow md:scale-105' : 'hover:glow-sm'
            }`}>
              {plan.popular && (
                <>
                  <div className="absolute inset-0 bg-gradient-to-br from-primary/10 via-transparent to-transparent pointer-events-none" />
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary text-primary-foreground text-xs font-bold px-4 py-1 rounded-full shadow-lg z-20">
                    Most Popular
                  </div>
                </>
              )}
              <CardHeader className="text-center relative z-10">
                <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center mx-auto mb-3">
                  <plan.icon className="h-6 w-6 text-primary" />
                </div>
                <CardTitle className="text-xl">{plan.name}</CardTitle>
                <div className="mt-4">
                  <span className="text-5xl font-bold text-foreground">{plan.price}</span>
                  <span className="text-muted-foreground ml-1">{plan.period}</span>
                </div>
              </CardHeader>
              <CardContent className="flex-1 flex flex-col relative z-10">
                <ul className="space-y-3 mb-8 flex-1">
                  {plan.features.map((f, j) => (
                    <motion.li
                      key={f}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.3 + j * 0.05 }}
                      className="flex items-center gap-2.5 text-sm text-foreground"
                    >
                      <div className="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                        <Check className="h-3 w-3 text-primary" />
                      </div>
                      {f}
                    </motion.li>
                  ))}
                </ul>
                <Button
                  className={`w-full h-11 ${plan.popular ? 'glow' : ''}`}
                  variant={plan.popular ? 'default' : 'outline'}
                >
                  {plan.price === '$0' ? 'Get Started' : 'Subscribe'}
                </Button>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  </Layout>
);

export default Pricing;
