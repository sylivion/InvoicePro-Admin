# -*- coding: utf-8 -*-
import sys
import os
import shutil

sys.stdout.reconfigure(encoding='utf-8')

def resolve_file(filepath):
    print(f"Resolving conflicts in {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Conflict 1: Sidebar Logo & Header
    c1_bad = '''<<<<<<< HEAD
    class="fixed lg:sticky top-0 z-50 lg:z-auto w-64 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col h-screen shadow-sm transition-transform duration-200">
    <!-- Logo -->
    <div class="px-4 py-4 border-b border-gray-100 flex items-center gap-3">
      <div class="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center flex-shrink-0">
        <i class="fa-solid fa-shield-halved text-white text-sm"></i>
      </div>
      <div>
        <div class="font-semibold text-base">Invoice<span class="text-brand-600">Pro</span></div>
        <div class="text-xs font-bold text-brand-500 tracking-widest uppercase" style="font-size:.6rem" x-text="rolePanelTitle">ADMIN PANEL</div>
=======
    class="fixed lg:sticky top-0 z-50 lg:z-auto w-56 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col h-screen shadow-sm transition-transform duration-200">
    <!-- Logo & Role Header -->
    <div class="px-4 py-3 border-b border-gray-100 dark:border-gray-800 flex flex-col gap-1 overflow-hidden">
      <div class="flex items-center justify-between">
        <img :src="appLogoUrl || 'assets/images/logo.png'" src="assets/images/logo.png" alt="InvoicePro" class="h-7 w-auto object-contain flex-shrink-0" />
      </div>
      <div class="flex items-center">
        <span class="text-[9px] font-bold px-2 py-0.5 rounded-md bg-brand-50 dark:bg-brand-950 text-brand-600 dark:text-brand-400 uppercase tracking-wider truncate max-w-full border border-brand-100 dark:border-brand-900" x-text="rolePanelTitle">ADMIN PANEL</span>
>>>>>>> e435756fd37b47570152ce5821f0ab7dd794be37'''

    c1_good = '''    class="fixed lg:sticky top-0 z-50 lg:z-auto w-56 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col h-screen shadow-sm transition-transform duration-200">
    <!-- Logo & Role Header -->
    <div class="px-4 py-3 border-b border-gray-100 dark:border-gray-800 flex flex-col gap-1 overflow-hidden">
      <div class="flex items-center justify-between">
        <img :src="appLogoUrl || 'assets/images/logo.png'" src="assets/images/logo.png" alt="InvoicePro" class="h-7 w-auto object-contain flex-shrink-0" />
      </div>
      <div class="flex items-center">
        <span class="text-[9px] font-bold px-2 py-0.5 rounded-md bg-brand-50 dark:bg-brand-950 text-brand-600 dark:text-brand-400 uppercase tracking-wider truncate max-w-full border border-brand-100 dark:border-brand-900" x-text="rolePanelTitle">ADMIN PANEL</span>'''

    if c1_bad in content:
        content = content.replace(c1_bad, c1_good)
        print("  Resolved Conflict 1 (Sidebar Logo)")

    # Conflict 2: Audit filter options
    c2_bad = '''<<<<<<< HEAD
              <option value="all">All Staff</option>
              <template x-for="u in auditFilterUserOptions" :key="u.username || u.name">
=======
              <option value="all">👤 All Staff</option>
              <template x-for="(u, idx) in auditFilterUserOptions" :key="u.key || ('opt_' + idx)">
>>>>>>> e435756fd37b47570152ce5821f0ab7dd794be37'''

    c2_good = '''              <option value="all">👤 All Staff</option>
              <template x-for="(u, idx) in auditFilterUserOptions" :key="u.key || ('opt_' + idx)">'''

    if c2_bad in content:
        content = content.replace(c2_bad, c2_good)
        print("  Resolved Conflict 2 (Audit Filter Options)")

    # Conflict 5: Audit log user_id
    c5_bad = '''<<<<<<< HEAD
            icon: icons[type] || '',
            user_id: user.id || user.emp_id || '',
=======
            icon: icons[type] || '📝',
            user_id: user.id || user.emp_id || user.username || '',
>>>>>>> e435756fd37b47570152ce5821f0ab7dd794be37'''

    c5_good = '''            icon: icons[type] || '📝',
            user_id: user.id || user.emp_id || user.username || '','''

    if c5_bad in content:
        content = content.replace(c5_bad, c5_good)
        print("  Resolved Conflict 5 (Audit Log Recording)")

    # Conflict 6: Normalize ticket helper
    c6_bad = '''<<<<<<< HEAD
        //  SUPPORT DEPARTMENT METHODS
=======
        _normalizeTicket(t) {
          if (!t || typeof t !== 'object') return t;
          const id = t.id || t.ticket_no || t.ticketNo || ('ST-' + Math.floor(100 + Math.random() * 900));
          const tNo = t.ticketNo || t.ticket_no || id;
          const cName = (t.customerName || t.customer_name || t.customer || t.name || 'Customer').trim();
          const phone = (t.phone || t.mobile || '').trim();
          const subj = (t.subject || t.title || t.issue || 'Support Request').trim();
          const cat = (t.category || t.issue_category || t.type || 'General Support').trim();
          const chan = (t.channel || t.source || 'Phone').trim();
          const rawPrio = (t.priority || 'Medium').toString().toLowerCase().trim();
          const prio = rawPrio === 'critical' ? 'Critical' : (rawPrio === 'high' ? 'High' : (rawPrio === 'low' ? 'Low' : 'Medium'));
          const status = (t.status || 'open').toString().toLowerCase().trim();
          const assigned = (t.assignedTo || t.assigned_to || t.assignee || '').toString().trim();
          
          t.id = id;
          t.ticketNo = tNo;
          t.ticket_no = tNo;
          t.customerName = cName;
          t.customer_name = cName;
          t.phone = phone;
          t.mobile = phone;
          t.subject = subj;
          t.category = (cat === 'undefined' || !cat) ? 'General Support' : cat;
          t.channel = (chan === 'undefined' || !chan) ? 'Phone' : chan;
          t.priority = prio;
          t.status = status;
          t.assignedTo = assigned;
          t.assigned_to = assigned;
          t.assignedToName = this.getTicketAssigneeName ? this.getTicketAssigneeName(t) : (t.assignedToName || t.assigned_to_name || 'Unassigned');
          return t;
        },

        // 🎧 SUPPORT DEPARTMENT METHODS
>>>>>>> e435756fd37b47570152ce5821f0ab7dd794be37'''

    c6_good = '''        _normalizeTicket(t) {
          if (!t || typeof t !== 'object') return t;
          const id = t.id || t.ticket_no || t.ticketNo || ('ST-' + Math.floor(100 + Math.random() * 900));
          const tNo = t.ticketNo || t.ticket_no || id;
          const cName = (t.customerName || t.customer_name || t.customer || t.name || 'Customer').trim();
          const phone = (t.phone || t.mobile || '').trim();
          const subj = (t.subject || t.title || t.issue || 'Support Request').trim();
          const cat = (t.category || t.issue_category || t.type || 'General Support').trim();
          const chan = (t.channel || t.source || 'Phone').trim();
          const rawPrio = (t.priority || 'Medium').toString().toLowerCase().trim();
          const prio = rawPrio === 'critical' ? 'Critical' : (rawPrio === 'high' ? 'High' : (rawPrio === 'low' ? 'Low' : 'Medium'));
          const status = (t.status || 'open').toString().toLowerCase().trim();
          const assigned = (t.assignedTo || t.assigned_to || t.assignee || '').toString().trim();
          
          t.id = id;
          t.ticketNo = tNo;
          t.ticket_no = tNo;
          t.customerName = cName;
          t.customer_name = cName;
          t.phone = phone;
          t.mobile = phone;
          t.subject = subj;
          t.category = (cat === 'undefined' || !cat) ? 'General Support' : cat;
          t.channel = (chan === 'undefined' || !chan) ? 'Phone' : chan;
          t.priority = prio;
          t.status = status;
          t.assignedTo = assigned;
          t.assigned_to = assigned;
          t.assignedToName = this.getTicketAssigneeName ? this.getTicketAssigneeName(t) : (t.assignedToName || t.assigned_to_name || 'Unassigned');
          return t;
        },

        // 🎧 SUPPORT DEPARTMENT METHODS'''

    if c6_bad in content:
        content = content.replace(c6_bad, c6_good)
        print("  Resolved Conflict 6 (Normalize Ticket)")

    # For Conflict 3 & 4 (Login Screen layout from origin/main):
    # Let's find any remaining <<<<<<< and >>>>>>> in the file
    lines = content.splitlines(keepends=True)
    out_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('<<<<<<<'):
            # scan until ======= and >>>>>>>
            head_lines = []
            main_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith('======='):
                head_lines.append(lines[i])
                i += 1
            if i < len(lines) and lines[i].startswith('======='):
                i += 1
            while i < len(lines) and not lines[i].startswith('>>>>>>>'):
                main_lines.append(lines[i])
                i += 1
            if i < len(lines) and lines[i].startswith('>>>>>>>'):
                i += 1
            
            # Default to main_lines for auth/login screen
            out_lines.extend(main_lines)
            print(f"  Resolved generic conflict at lines {len(out_lines)}")
        else:
            out_lines.append(line)
            i += 1

    content = "".join(out_lines)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Finished resolving {filepath}!")

if __name__ == '__main__':
    resolve_file('AdminPanel.html')
    resolve_file('index.html')
    sub_path = os.path.join('InvoicePro Admin', 'AdminPanel.html')
    if os.path.exists(sub_path):
        resolve_file(sub_path)
