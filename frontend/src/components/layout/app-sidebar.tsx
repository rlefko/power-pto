import { useLocation, Link } from "react-router";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useAuth } from "@/lib/auth/use-auth";
import { Calendar, CheckCircle, FileText, PartyPopper, ScrollText, Users, Wallet } from "lucide-react";

const employeeNavItems = [
  { title: "My Balances", href: "/balances", icon: Wallet },
  { title: "My Requests", href: "/requests", icon: Calendar },
];

const adminNavItems = [
  { title: "Policies", href: "/policies", icon: FileText },
  { title: "Employees", href: "/employees", icon: Users },
  { title: "Approvals", href: "/approvals", icon: CheckCircle },
  { title: "Holidays", href: "/holidays", icon: PartyPopper },
  { title: "Audit Log", href: "/audit-log", icon: ScrollText },
];

export function AppSidebar() {
  const { pathname } = useLocation();
  const { role } = useAuth();
  const isAdmin = role === "admin";

  return (
    <Sidebar>
      <SidebarHeader className="border-b px-4 py-3">
        <Link to="/" className="text-lg font-bold tracking-tight">
          Power PTO
        </Link>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Employee</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {employeeNavItems.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton asChild isActive={pathname.startsWith(item.href)}>
                    <Link to={item.href}>
                      <item.icon className="h-4 w-4" />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {isAdmin && (
          <SidebarGroup>
            <SidebarGroupLabel>Admin</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {adminNavItems.map((item) => (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton asChild isActive={pathname.startsWith(item.href)}>
                      <Link to={item.href}>
                        <item.icon className="h-4 w-4" />
                        <span>{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>
    </Sidebar>
  );
}
