import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/lib/auth/use-auth";

const DEV_USERS = [
  { id: "00000000-0000-0000-0000-000000000001", label: "Admin User" },
  { id: "00000000-0000-0000-0000-000000000002", label: "Alice Johnson" },
  { id: "00000000-0000-0000-0000-000000000003", label: "Bob Smith" },
  { id: "00000000-0000-0000-0000-000000000004", label: "Carol Williams" },
  { id: "00000000-0000-0000-0000-000000000005", label: "Dave Brown" },
];

export function AppHeader() {
  const { role, setRole, userId, setUserId } = useAuth();

  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b px-4">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-2 h-4" />
      <div className="flex flex-1 items-center justify-between">
        <span className="text-sm text-muted-foreground">Power PTO</span>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground">User:</span>
            <Select value={userId} onValueChange={setUserId}>
              <SelectTrigger className="h-7 w-[150px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DEV_USERS.map((u) => (
                  <SelectItem key={u.id} value={u.id}>
                    {u.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Role:</span>
            <Select value={role} onValueChange={setRole}>
              <SelectTrigger className="h-7 w-[110px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="admin">Admin</SelectItem>
                <SelectItem value="employee">Employee</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>
    </header>
  );
}
