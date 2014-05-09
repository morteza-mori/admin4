# The Admin4 Project
# (c) 2013-2014 Andreas Pflug
#
# Licensed under the Apache License, 
# see LICENSE.TXT for conditions of usage


import wx.aui, wx.stc, wx.grid
import adm
import xmlres
from wh import xlt, GetBitmap, Menu, modPath, floatToTime, AcceleratorHelper
from _explain import ExplainCanvas, ExplainText
from _snippet import SnippetTree


NULLSTRING="(NULL)"

STATUSPOS_MSGS=1
STATUSPOS_POS=2
STATUSPOS_ROWS=3
STATUSPOS_SECS=4

class SqlEditor(wx.stc.StyledTextCtrl):
  pass


class SqlResultGrid(wx.grid.Grid):
  HMARGIN=5
  VMARGIN=5
  
  def __init__(self, parent):
    wx.grid.Grid.__init__(self, parent)
    self.CreateGrid(0,0)
    self.SetColLabelSize(0)
    self.SetRowLabelSize(0)
    self.AutoSize()
    
  def SetEmpty(self):
    self.SetTable(wx.grid.GridStringTable(0,0))
    self.SetColLabelSize(0)
    self.SetRowLabelSize(0)
    self.SendSizeEventToParent()

  
  def SetData(self, rowset):
    rowcount=rowset.GetRowcount()
    colcount=len(rowset.colNames)
    
    if rowcount<0:
      rowcount=0
    self.SetTable(wx.grid.GridStringTable(rowcount, colcount))
    w,h=self.GetTextExtent('Colname')
    self.SetColLabelSize(h+self.HMARGIN)
    self.SetRowLabelSize(w+self.VMARGIN)
    self.SetDefaultRowSize(h+self.HMARGIN)
    
    self.previousCols=rowset.colNames
    self.Freeze()
    self.BeginBatch()
    for x in range(colcount):
      colname=rowset.colNames[x]
      if colname == '?column?':
        colname="Col #%d" % (x+1)
      self.SetColLabelValue(x, colname)
    y=0  
    for row in rowset:
      self.SetRowLabelValue(y, "%d" % (y+1))
      for x in range(colcount):
        val=row[x]
        if val == None:
          val=NULLSTRING
        else:
          val=unicode(val)
        self.SetCellValue(y, x, val)
        self.SetReadOnly(y,x) 
      y = y+1
    self.EndBatch()
    self.AutoSizeColumns()
    self.Thaw()
    self.SendSizeEventToParent()
    
  def Paste(self):
    pass
  
  def Cut(self):
    self.Copy()
  
  def Copy(self):
    vals=self.getCells()
    if vals:
      adm.SetClipboard(vals)


  def getCells(self, quoteChar="'", commaChar=', ', lfChar='\n', null='NULL'):
    def quoted(v):
      if v == NULLSTRING:
        return null
      try:
        _=float(v)
        return v
      except:
        return "%s%s%s" % (quoteChar, v, quoteChar) 
    
    vals=[]
    cells=self.GetSelectedCells()
    if cells:
      for row,col in cells:
        vals.append(quoted(self.GetCellValue(row, col)))
        return commaChar.join(vals)
    else:
      rows=self.GetSelectedRows()
      if rows:
        cols=range(self.GetTable().GetColsCount())
      else:
        cols=self.GetSelectedCols()
        if cols:
          rows=range(self.GetTable().GetRowsCount())
        else:
          return None
      for row in rows:
        v=[]
        for col in cols:
          v.append(quoted(self.GetCellValue(row, col)))
        vals.append(commaChar.join(v))
      return lfChar.join(vals)
    
    
class SqlFrame(adm.Frame):
  def __init__(self, _parentWin, node):
    style=wx.MAXIMIZE_BOX|wx.RESIZE_BORDER|wx.SYSTEM_MENU|wx.CAPTION|wx.CLOSE_BOX
    adm.Frame.__init__(self, None, xlt("Query Tool"), style, (600,400), None)
    self.SetIcon(wx.Icon(modPath("SqlQuery.ico", self)))

    self.server=node.GetServer()
    self.application="Admin4 Query Tool"
    
    if hasattr(node, "GetDatabase"):
      dbName=node.GetDatabase().name
    else:
      dbName=self.server.maintDb
    self.worker=None
    self.sqlChanged=False
    self.currentFile=None
    self.previousCols=[]


    self.toolbar=self.CreateToolBar(wx.TB_FLAT|wx.TB_NODIVIDER)
    self.toolbar.SetToolBitmapSize(wx.Size(16, 16));

    self.toolbar.DoAddTool(self.GetMenuId(self.OnFileOpen), xlt("Load from file"), GetBitmap("file_open", self))
    self.toolbar.DoAddTool(self.GetMenuId(self.OnFileSave), xlt("Save to file"), GetBitmap("file_save", self))
    self.toolbar.DoAddTool(self.GetMenuId(self.OnShowSnippets), xlt("Show snippets browser"), GetBitmap("snippets", self))
    self.toolbar.AddSeparator()
    self.toolbar.DoAddTool(self.GetMenuId(self.OnUndo), xlt("Undo"), GetBitmap("edit_undo", self))
    self.toolbar.DoAddTool(self.GetMenuId(self.OnRedo), xlt("Redo"), GetBitmap("edit_redo", self))
    self.toolbar.DoAddTool(self.GetMenuId(self.OnClear), xlt("Clear"), GetBitmap("edit_clear", self))
    self.toolbar.DoAddTool(self.GetMenuId(self.OnClear), xlt("Find"), GetBitmap("edit_find", self))
    self.toolbar.AddSeparator()
    self.toolbar.DoAddTool(self.GetMenuId(self.OnAddSnippet), xlt("Add snippet"), GetBitmap("snippet_add", self))
    self.toolbar.DoAddTool(self.GetMenuId(self.OnReplaceSnippet), xlt("Replace snippet"), GetBitmap("snippet_replace", self))
    self.toolbar.AddSeparator()
    
    cbClass=xmlres.getControlClass("whComboBox")
    allDbs=self.server.GetConnectableDbs()
    size=max(map(lambda db: self.toolbar.GetTextExtent(db)[0], allDbs))
    
    BUTTONOFFS=30
    self.databases=cbClass(self.toolbar, size=(size+BUTTONOFFS, -1))
    self.databases.Append(allDbs)

    self.databases.SetStringSelection(dbName)
    self.OnChangeDatabase()
    self.databases.Bind(wx.EVT_COMBOBOX, self.OnChangeDatabase)
    self.toolbar.AddControl(self.databases)
    self.toolbar.DoAddTool(self.GetMenuId(self.OnExecuteQuery), xlt("Execute Query"), GetBitmap("query_execute", self))
    self.toolbar.DoAddTool(self.GetMenuId(self.OnExplainQuery), xlt("Explain Query"), GetBitmap("query_explain", self))
    self.toolbar.DoAddTool(self.GetMenuId(self.OnCancelQuery), xlt("Execute Query"), GetBitmap("query_cancel", self))
    self.toolbar.Realize()

    menubar=wx.MenuBar()
    self.filemenu=menu=Menu()

    self.AddMenu(menu, xlt("&Open"), xlt("Open query file"), self.OnFileOpen)
    self.AddMenu(menu, xlt("&Insert"), xlt("Insert query file"), self.OnFileInsert)
    self.AddMenu(menu, xlt("&Save"), xlt("Save current file"), self.OnFileSave)
    self.AddMenu(menu, xlt("Save &as.."), xlt("Save file under new name"), self.OnFileSaveAs)
    menu.AppendSeparator()
    self.AddMenu(menu, xlt("Show snippets"), xlt("Show snippet browser"), self.OnShowSnippets)
    
    if wx.Platform != "__WXMAC__":
      menu.AppendSeparator()
    #self.AddMenu(menu, xlt("Preferences"), xlt("Preferences"), self.OnPreferences, wx.ID_PREFERENCES, adm.app.SetMacPreferencesMenuItemId)
    #self.AddMenu(menu, xlt("Quit"), xlt("Quit Admin4"), self.OnQuit, wx.ID_EXIT, adm.app.SetMacExitMenuItemId)

    menubar.Append(menu, xlt("&File"))

    self.editmenu=menu=Menu()
    self.AddMenu(menu, xlt("&Undo"), xlt("Undo last action"), self.OnUndo)
    self.AddMenu(menu, xlt("&Redo"), xlt("Redo last action"), self.OnRedo)
    self.AddMenu(menu, xlt("C&lear"), xlt("Clear editor"), self.OnClear)
    self.AddMenu(menu, xlt("&Find"), xlt("Find string"), self.OnFind)
    menu.AppendSeparator()
    self.AddMenu(menu, xlt("Cu&t"), xlt("Cut selected text to clipboard"), self.OnCut)
    self.AddMenu(menu, xlt("&Copy"), xlt("Copy selected text to clipboard"), self.OnCopy)
    self.AddMenu(menu, xlt("&Paste"), xlt("Paste text from clipboard"), self.OnPaste)
    menu.AppendSeparator()
    self.AddMenu(menu, xlt("Add snippet"), xlt("Add selected text to snippets"), self.OnAddSnippet)
    self.AddMenu(menu, xlt("Modify snippet"), xlt("Replace snippet with selected text"), self.OnReplaceSnippet)
    menubar.Append(menu, xlt("&Edit"))
    
    self.querymenu=menu=Menu()
    self.AddMenu(menu, xlt("Execute"), xlt("Execute query"), self.OnExecuteQuery)
    self.AddMenu(menu, xlt("Explain"), xlt("Explain query"), self.OnExplainQuery)
    self.AddMenu(menu, xlt("Cancel"), xlt("Cancel query execution"), self.OnCancelQuery)
    menubar.Append(menu, xlt("&Query"))
    
    self.EnableMenu(self.querymenu, self.OnCancelQuery, False)
    self.SetMenuBar(menubar)
    
    ah=AcceleratorHelper(self)
    ah.Add(wx.ACCEL_CTRL, 'X', self.OnCut)
    ah.Add(wx.ACCEL_CTRL, 'C', self.OnCopy)
    ah.Add(wx.ACCEL_CTRL, 'V', self.OnPaste)
    ah.Add(wx.ACCEL_NORMAL,wx.WXK_F5, self.OnExecuteQuery)
    ah.Add(wx.ACCEL_NORMAL,wx.WXK_F7, self.OnExplainQuery)
    ah.Add(wx.ACCEL_ALT,wx.WXK_PAUSE, self.OnCancelQuery)
    ah.Realize()
 
    self.manager=wx.aui.AuiManager(self)
    self.manager.SetFlags(wx.aui.AUI_MGR_ALLOW_FLOATING|wx.aui.AUI_MGR_TRANSPARENT_HINT | \
         wx.aui.AUI_MGR_HINT_FADE| wx.aui.AUI_MGR_TRANSPARENT_DRAG)

    pt=self.GetFont().GetPointSize()
    font=wx.Font(pt, wx.TELETYPE, wx.NORMAL, wx.NORMAL)

    self.input=SqlEditor(self)
    self.input.StyleSetFont(0, font)
    self.input.MarkerDefineBitmap(0, GetBitmap("badline", self))
    self.input.SetAcceleratorTable(ah.GetTable())
    self.input.Bind(wx.stc.EVT_STC_UPDATEUI, self.OnStatusPos)
    self.input.Bind(wx.stc.EVT_STC_CHANGE, self.OnChangeStc)
    self.manager.AddPane(self.input, wx.aui.AuiPaneInfo().Top().PaneBorder().Resizable().MinSize((200,100)).BestSize((400,200)).CloseButton(False) \
                          .Name("sqlQuery").Caption(xlt("SQL Query")))
    
    
    self.snippets=SnippetTree(self, self.server, self.input)
    self.manager.AddPane(self.snippets, wx.aui.AuiPaneInfo().Left().Top().PaneBorder().Resizable().MinSize((100,100)).BestSize((100,100)).CloseButton(True) \
                          .Name("snippets").Caption(xlt("SQL Snippets")))

    
    self.output=wx.Notebook(self)
    self.result=SqlResultGrid(self.output)
    self.explain = ExplainCanvas(self.output)
    self.explain.Hide()
    
    self.messages=wx.TextCtrl(self.output, style=wx.TE_MULTILINE|wx.TE_READONLY|wx.TE_DONTWRAP)
    self.msgHistory=wx.TextCtrl(self.output, style=wx.TE_MULTILINE|wx.TE_READONLY|wx.TE_DONTWRAP)
    self.messages.SetFont(font)
    self.msgHistory.SetFont(font)

    self.output.AddPage(self.result, xlt("Output"))
    self.output.AddPage(self.messages, xlt("Messages"))
    self.output.AddPage(self.msgHistory, xlt("History"))
        
    self.manager.AddPane(self.output, wx.aui.AuiPaneInfo().Center().MinSize((200,100)).BestSize((400,200)).CloseButton(False) \
                          .Name("Result").Caption(xlt("Result")).CaptionVisible(False))

    self.CreateStatusBar(5, wx.ST_SIZEGRIP)
    w,_h=self.StatusBar.GetTextExtent('Mg')
    self.SetStatusWidths([0, -1, 5*w,6*w,5*w])
    self.SetStatus(xlt("ready"))
    
    str=adm.config.GetPerspective(self)
    #str=None
    if str:
      self.manager.LoadPerspective(str)

    self.Bind(wx.EVT_CLOSE, self.OnClose)
    self.manager.Update()
    self.updateMenu()

  
  def SetTitle(self, dbName):
    title=xlt("PostGreSQL Query Tool - Database \"%(dbname)s\" on Server \"%(server)s\""  % { 'dbname': dbName, 'server': self.server.name})
    adm.Frame.SetTitle(self, title)


  def OnClose(self, evt):
    for i in range(self.databases.GetCount()):
      conn=self.databases.GetClientData(i)
      if conn:
        conn.disconnect()
    adm.config.storeWindowPositions(self)
    self.Destroy()
      
    
  def OnChangeDatabase(self, evt=None):
    i=self.databases.GetSelection()
    if i >= 0:
      dbName=self.databases.GetString(i)
      self.conn = self.databases.GetClientData(i)
      if not self.conn:
        self.conn = self.server.DoConnect(dbName, application=self.application)
        self.databases.SetClientData(i, self.conn)
      self.SetTitle(dbName)
        

  def updateMenu(self, ctl=None):
    if not self.GetToolBar():
      return
    canCut=canPaste=canUndo=canRedo=False
    if not ctl or ctl == self.input:
      canUndo=self.input.CanUndo();
      canRedo=self.input.CanRedo();
      canPaste=self.input.CanPaste();
      canCut = True;
    
    a,e=self.input.GetSelection()
    canQuery = ( a!=e or self.input.GetLineCount() >1 or self.getSql() )


    self.EnableMenu(self.editmenu, self.OnAddSnippet, self.server.GetValue('snippet_table'))
    self.EnableMenu(self.editmenu, self.OnReplaceSnippet, self.snippets.CanReplace())
    self.EnableMenu(self.editmenu, self.OnCut, canCut)
    self.EnableMenu(self.editmenu, self.OnPaste, canPaste)
    self.EnableMenu(self.editmenu, self.OnUndo, canUndo)
    self.EnableMenu(self.editmenu, self.OnRedo, canRedo)
    self.EnableMenu(self.editmenu, self.OnClear, canQuery)
    self.EnableMenu(self.editmenu, self.OnFind, canQuery)
    
    self.EnableMenu(self.filemenu, self.OnFileSave, self.sqlChanged)
    
    self.EnableMenu(self.querymenu, self.OnExecuteQuery, canQuery)
    self.EnableMenu(self.querymenu, self.OnExplainQuery, canQuery)
    
    
  def executeSql(self, targetPage, sql, _queryOffset=0, resultToMsg=False):
    self.EnableMenu(self.querymenu, self.OnCancelQuery, True)
    self.EnableMenu(self.querymenu, self.OnExecuteQuery, False)
    self.EnableMenu(self.querymenu, self.OnExplainQuery, False)
    
    self.worker=worker=self.conn.ExecuteAsync(sql)
    rowcount=0
    rowset=None
    worker.start()
    
    self.SetStatus(xlt("Query is running."));
    self.SetStatusText("", STATUSPOS_SECS);
    self.SetStatusText("", STATUSPOS_ROWS);     
    self.msgHistory.AppendText(xlt("-- Executing query:\n"));
    self.msgHistory.AppendText(sql);
    self.msgHistory.AppendText("\n");
    self.input.MarkerDeleteAll(0)    
    self.messages.Clear()
    
    startTime=wx.GetLocalTimeMillis();
    
    while worker.IsRunning():
      elapsed=wx.GetLocalTimeMillis() - startTime
      self.SetStatusText(floatToTime(elapsed/1000.), STATUSPOS_SECS)
      wx.Yield()
      if elapsed < 200:
        wx.MilliSleep(10);
      elif elapsed < 10000:
        wx.MilliSleep(100);
      else:
        wx.MilliSleep(500)
      wx.Yield()
    
    self.worker=None
    elapsed=wx.GetLocalTimeMillis() - startTime
    if elapsed:
      txt=floatToTime(elapsed/1000.)
    else:
      txt="0 ms"
    self.SetStatusText(txt, STATUSPOS_SECS)
    self.EnableMenu(self.querymenu, self.OnCancelQuery, False)
    self.EnableMenu(self.querymenu, self.OnExecuteQuery, True)
    self.EnableMenu(self.querymenu, self.OnExplainQuery, True)

    if worker.error:
      errmsg=worker.error.error.decode('utf8')
      errlines=errmsg.splitlines()

      self.messages.SetValue(errmsg)
      self.msgHistory.AppendText(errmsg)
      for i in range(1, len(errlines)-2):
        if errlines[i].startswith("LINE "):
          lineinfo=errlines[i].split(':')[0][5:]
          colinfo=errlines[i+1].find('^')
          dummy=colinfo
          self.input.MarkerAdd(0, int(lineinfo))
          break

    if worker.cancelled:
      self.SetStatus(xlt("Cancelled."));
    elif worker.error:
      self.SetStatus(errlines[0]);
    else:
      self.SetStatus(xlt("OK."));
      
      rowcount=worker.GetRowcount()
      rowset=worker.GetResult()


    if worker.error:
      self.SetStatusText("", STATUSPOS_ROWS)
    else:
      if rowcount == 1:
        rowsMsg=xlt("1 row affected")
      elif rowcount < 0:
        rowsMsg=xlt("Executed")
      else:
        rowsMsg= xlt("%d rows affected") % rowcount
      self.SetStatusText(rowsMsg, STATUSPOS_ROWS)
      self.msgHistory.AppendText("-- %s\n" % rowsMsg)
    
      
    self.msgHistory.AppendText("\n")
    currentPage=self.output.GetPage(0)
    if currentPage != targetPage:
      self.output.RemovePage(0)
      currentPage.Hide()
      targetPage.Show()
      self.output.InsertPage(0, targetPage, xlt("Data output"), True)

    if rowset:
      self.output.SetSelection(0)
      targetPage.SetData(rowset)
    else:
      self.output.SetSelection(1)
      targetPage.SetEmpty()

    for notice in self.conn.conn.notices:
      self.messages.AppendText(notice);
      self.messages.AppendText("\n")

    if not worker.error:
      if resultToMsg:
        self.messages.SetValue("\n".join(targetPage.GetResult()))
      else:
        self.messages.SetValue(rowsMsg)

    self.input.SetFocus()


  def SetStatus(self, status):
    self.SetStatusText(status, STATUSPOS_MSGS)
  
  def getSql(self):  
    sql=self.input.GetSelectedText()
    if not sql:
      sql=self.input.GetText()
    return sql.strip()
  
  
  def OnShowSnippets(self, evt):
    self.manager.GetPane("snippets").Show(True)
    self.manager.Update()    
  
  def OnAddSnippet(self, evt):
    sql=self.getSql()
    if sql:
      dlg=wx.TextEntryDialog(self, xlt("Snippet name"), xlt("Add snippet"))
      if dlg.ShowModal() == wx.ID_OK:
        name=dlg.GetValue()
        self.snippets.AppendSnippet(name, sql)
        self.SetStatus(xlt("Snipped stored."))
    
  def OnReplaceSnippet(self, evt):
    sql=self.getSql()
    if sql:
      self.snippets.ReplaceSnippet(sql)


  def OnCancelQuery(self, evt):
    self.EnableMenu(self.querymenu, self.OnCancelQuery, False)
    if self.worker:
      self.worker.Cancel()

  def OnExecuteQuery(self, evt):
    sql=self.getSql()
    if not sql.strip():
      return
    self.executeSql(self.result, sql)

  def OnExplainQuery(self, evt):
    sql=self.getSql()
    if not sql:
      return
    self.executeSql(self.explain, "EXPLAIN %s" % sql, 8, True)

  
  def getFile(self):
    return ""
  
  def OnFileOpen(self, evt):
    sql=self.readFile()
    if sql:
      self.editor.ClearAll()
      self.editor.ReplaceSelection(sql)
      self.updateMenu()
      
  
  def OnFileInsert(self, evt):
    sql=self.getFile()
    if sql:
      self.editor.ReplaceSelection(sql)
      self.updateMenu()
  
  def writeFile(self, fn):
    if self.currentFile != fn:
      self.currentFile = fn
      
  def OnFileSave(self, evt):
    if not self.currentFile:
      return self.OnFileSaveAs(evt)
    self.writeFile(self.currentFile)
  
  def OnFileSaveAs(self, evt):
    pass
  
  def OnUndo(self, evt):
    self.input.Undo()
  
  def OnClear(self, evt):
    self.input.ClearAll()
    self.updateMenu()
    
  def OnFind(self, evt):
    pass
  
  def OnRedo(self, evt):
    self.input.Redo()
  
  def OnCut(self, evt):
    wnd=wx.Window.FindFocus()
    if wnd:
      wnd.Cut()
  
  def OnCopy(self, evt):
    wnd=wx.Window.FindFocus()
    if wnd:
      wnd.Copy()
  
  def OnPaste(self, evt):
    wnd=wx.Window.FindFocus()
    if wnd:
      wnd.Paste()
  
  def OnChangeStc(self, evt):
    self.sqlChanged=True
    self.updateMenu()
    
  def OnStatusPos(self, evt):

    row=self.input.LineFromPosition(self.input.GetCurrentPos())+1
    col=self.input.GetColumn(self.input.GetCurrentPos())+1
    self.SetStatusText(xlt("Ln %d Col %d") % (row, col), STATUSPOS_POS)
    
    
    
############################################################
# node menu

class QueryTool:
  name=xlt("Query Tool")
  help=xlt("Execute SQL Queries")
  toolbitmap='SqlQuery'
  
  @staticmethod
  def CheckAvailableOn(_node):
    return True
  
  @staticmethod
  def CheckEnabled(_node):
    return True

  @staticmethod
  def OnExecute(parentWin, node):
    frame=SqlFrame(parentWin, node)
    frame.Show()
    return None

nodeinfo=[]
menuinfo=[ {"class": QueryTool, "sort": 30 }, ]

    