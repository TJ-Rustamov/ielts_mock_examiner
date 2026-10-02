import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { BookOpen, KeyRound, Upload } from 'lucide-react';
import AdminLayout from '@/components/admin/AdminLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  errorMessage, listAdminModules, setModulePublished, type AdminModule, type Skill,
} from '@/lib/exams';

function KeyBadge({ module }: { module: AdminModule }) {
  if (!module.has_answer_sheet) return <Badge variant="outline">No key</Badge>;
  if (module.answer_sheet_verified) {
    return <Badge className="bg-emerald-600 hover:bg-emerald-600">Verified</Badge>;
  }
  // How many answers still need a person - not which, and not what they are.
  const counts = module.answer_sheet_counts;
  const outstanding = counts ? counts.check + counts.missing : null;
  return (
    <Badge className="bg-amber-500 hover:bg-amber-500">
      {outstanding === null
        ? 'Needs checking'
        : outstanding === 0 ? 'Ready to verify' : `${outstanding} to check`}
    </Badge>
  );
}

const ExamModules = () => {
  const navigate = useNavigate();
  const [modules, setModules] = useState<AdminModule[] | null>(null);
  const [skill, setSkill] = useState<'all' | Skill>('all');
  const [busy, setBusy] = useState<number | null>(null);

  useEffect(() => {
    listAdminModules()
      .then((response) => setModules(response.modules))
      .catch((error) => toast.error(errorMessage(error, 'Could not load tests.')));
  }, []);

  const books = useMemo(() => {
    const grouped = new Map<string, AdminModule[]>();
    (modules ?? [])
      .filter((module) => skill === 'all' || module.skill === skill)
      .forEach((module) => {
        const list = grouped.get(module.book) ?? [];
        list.push(module);
        grouped.set(module.book, list);
      });
    grouped.forEach((list) => list.sort(
      (a, b) => a.test_number - b.test_number || a.skill.localeCompare(b.skill),
    ));
    return [...grouped.entries()];
  }, [modules, skill]);

  const togglePublished = async (module: AdminModule, next: boolean) => {
    setBusy(module.id);
    try {
      const updated = await setModulePublished(module.id, next);
      setModules((previous) => (previous ?? []).map((m) => (m.id === updated.id ? updated : m)));
      toast.success(next ? 'Test is now available to students' : 'Test hidden from students');
    } catch (error) {
      toast.error(errorMessage(error, 'Could not change this test.'));
    } finally {
      setBusy(null);
    }
  };

  const live = (modules ?? []).filter((m) => m.is_published).length;

  return (
    <AdminLayout>
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold">
              <BookOpen className="h-6 w-6 text-primary" /> Reading & Listening
            </h1>
            <p className="text-sm text-muted-foreground">
              A test is visible to students only once its answer key has been verified by a person.
              {modules && ` ${live} of ${modules.length} live.`}
            </p>
          </div>
          <Button onClick={() => navigate('/admin/exams/import')}>
            <Upload className="mr-2 h-4 w-4" /> Import a book
          </Button>
        </div>

        <Tabs value={skill} onValueChange={(value) => setSkill(value as 'all' | Skill)}>
          <TabsList>
            <TabsTrigger value="all">All</TabsTrigger>
            <TabsTrigger value="reading">Reading</TabsTrigger>
            <TabsTrigger value="listening">Listening</TabsTrigger>
          </TabsList>
        </Tabs>

        {modules === null && <Skeleton className="h-72 rounded-xl" />}

        {modules !== null && books.length === 0 && (
          <Card>
            <CardContent className="py-10 text-center text-muted-foreground">
              No tests yet. Import a book to get started.
            </CardContent>
          </Card>
        )}

        {books.map(([book, list]) => (
          <Card key={book}>
            <CardHeader>
              <CardTitle className="text-lg">{book}</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Test</TableHead>
                    <TableHead>Skill</TableHead>
                    <TableHead>Questions</TableHead>
                    <TableHead>Answer key</TableHead>
                    <TableHead>What is blocking it</TableHead>
                    <TableHead className="text-right">Live</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {list.map((module) => {
                    const blocked = module.blocking_problems.length > 0;
                    return (
                      <TableRow key={module.id}>
                        <TableCell className="font-medium">Test {module.test_number}</TableCell>
                        <TableCell className="capitalize">{module.skill}</TableCell>
                        <TableCell className="tabular-nums">{module.total_questions}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <KeyBadge module={module} />
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => navigate(`/admin/exams/modules/${module.id}/answer-sheet`)}
                            >
                              <KeyRound className="mr-1 h-4 w-4" /> Open
                            </Button>
                          </div>
                        </TableCell>
                        <TableCell className="max-w-xs text-xs text-muted-foreground">
                          {blocked ? module.blocking_problems.join('; ') : 'Ready'}
                        </TableCell>
                        <TableCell className="text-right">
                          <Switch
                            checked={module.is_published}
                            disabled={busy === module.id || (!module.is_published && blocked)}
                            onCheckedChange={(next) => void togglePublished(module, next)}
                            aria-label={`Publish Test ${module.test_number} ${module.skill}`}
                          />
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        ))}
      </div>
    </AdminLayout>
  );
};

export default ExamModules;
