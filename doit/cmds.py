"""cmd-line functions"""
import sys
import os.path
import itertools

from doit import dependency
from doit.task import Task
from doit.main import TaskSetup, InvalidCommand
from doit.runner import run_tasks
from doit.reporter import REPORTERS
from doit.dependency import Dependency


def doit_run(dependencyFile, task_list, output, options=None,
             verbosity=None, alwaysExecute=False, continue_=False,
             reporter='default'):
    # get tasks to be executed
    selected_tasks = TaskSetup(task_list, options).process()
    if reporter not in REPORTERS:
        msg = ("No reporter named '%s'.\nType 'doit help run' to see a list "
               "of available reporters.")
        raise InvalidCommand(msg % reporter)
    reporter_cls = REPORTERS[reporter]

    if verbosity is None:
        use_verbosity = Task.DEFAULT_VERBOSITY
    else:
        use_verbosity = verbosity
    show_out = use_verbosity < 2 # show on error report

    if isinstance(output, str):
        outstream = open(output, 'w')
    else: # outfile is a file-like object (like StringIO or sys.stdout)
        outstream = output
    try:
        # FIXME stderr will be shown twice in case of task error/failure
        reporter_obj = reporter_cls(outstream, show_out , True)

        return run_tasks(dependencyFile, selected_tasks, reporter_obj,
                         verbosity, alwaysExecute, continue_)
    finally:
        if isinstance(output, str):
            outstream.close()



def doit_clean(task_list, outstream, dryrun, clean_tasks):
    """Clean tasks
    @param task_list (list - L{Task}): list of all tasks from dodo file
    @param clean_tasks (list - string): tasks bo be clean. clean all if
                                        empty list.
    """
    if not clean_tasks:
        # clean all tasks
        for task_ in task_list:
            task_.clean(outstream, dryrun)
    else:
        tasks = dict([(t.name, t) for t in task_list])
        for name in clean_tasks:
            tasks[name].clean(outstream, dryrun)



def doit_list(dependencyFile, task_list, outstream, filter_tasks,
              print_subtasks=False, print_doc=False, print_status=False,
              print_private=False):
    """List task generators, in the order they were defined.

    @param filter_tasks (list -str): print only tasks from this list
    @param outstream (file-like): object
    @param print_subtasks (bool)
    @param print_doc(bool)
    @param print_status(bool)
    @param print_private(bool)
    """
    status_map = {'ignore': 'I', 'up-to-date': 'U', 'run': 'R'}
    def _list_print_task(task):
        """print a single task"""
        task_str = task.name
        # add doc
        if print_doc and task.doc:
            task_str += "\t* %s" % task.doc
        if print_status:
            task_uptodate = dependencyManager.get_status(task)
            task_str = "%s %s" % (status_map[task_uptodate], task_str)

        outstream.write("%s\n" % task_str)
        # print subtasks
        if print_subtasks:
            for subt in task.task_dep:
                if subt.startswith("%s" % task.name):
                    _list_print_task(tasks[subt])

    # dict of all tasks
    tasks = dict([(t.name, t) for t in task_list])
    # list only tasks passed on command line
    if filter_tasks:
        print_tasks = [tasks[name] for name in filter_tasks]
    else:
        print_tasks = task_list
    # status
    if print_status:
        dependencyManager = Dependency(dependencyFile)

    for task in print_tasks:
        # exclude subtasks (never exclude if filter specified)
        if (not filter_tasks) and task.is_subtask:
            continue
        # exclude private tasks
        if (not print_private) and task.name.startswith('_'):
            continue
        _list_print_task(task)
    return 0


def doit_forget(dbFileName, taskList, outstream, forgetTasks):
    """remove saved data successful runs from DB
    @param dbFileName: (str)
    @param task_list: (Task) tasks from dodo file
    @param forget_tasks: (list - str) tasks to be removed. remove all if
                         empty list.
    """
    dependencyManager = dependency.Dependency(dbFileName)
    # no task specified. forget all
    if not forgetTasks:
        dependencyManager.remove_all()
        outstream.write("forgeting all tasks\n")
    # forget tasks from list
    else:
        tasks = dict([(t.name, t) for t in taskList])
        for taskName in forgetTasks:
            # check task exist
            if taskName not in tasks:
                msg = "'%s' is not a task."
                raise InvalidCommand(msg % taskName)
            # for group tasks also remove all tasks from group.
            group = [taskName]
            while group:
                to_forget = group.pop(0)
                if not tasks[to_forget].actions:
                    # get task dependencies only from group-task
                    group.extend(tasks[to_forget].task_dep)
                # forget it - remove from dependency file
                dependencyManager.remove(to_forget)
                outstream.write("forgeting %s\n" % to_forget)
    dependencyManager.close()


def doit_ignore(dbFileName, taskList, outstream, ignoreTasks):
    """mark tasks to be ignored
    @param dbFileName: (str)
    @param taskList: (Task) tasks from dodo file
    @param ignoreTasks: (list - str) tasks to be ignored.
    """
    # no task specified.
    if not ignoreTasks:
        outstream.write("You cant ignore all tasks! Please select a task.\n")
        return

    dependencyManager = dependency.Dependency(dbFileName)
    tasks = dict([(t.name, t) for t in taskList])
    for taskName in ignoreTasks:
        # check task exist
        if taskName not in tasks:
            msg = "'%s' is not a task."
            raise InvalidCommand(msg % taskName)
        # for group tasks also remove all tasks from group.
        # FIXME: DRY
        group = [taskName]
        while group:
            to_ignore = group.pop(0)
            if not tasks[to_ignore].actions:
                # get task dependencies only from group-task
                group.extend(tasks[to_ignore].task_dep)
            # ignore it - remove from dependency file
            dependencyManager.ignore(tasks[to_ignore])
            outstream.write("ignoring %s\n" % to_ignore)
    dependencyManager.close()



class FileModifyWatcher(object):
    """Use inotify to watch file-system for file modifications

    Usage:
    1) subclass the method handle_event, action to be performed
    2) create an object passing a list of files to be watched
    3) call the loop method
    """
    def __init__(self, file_list):
        """@param file_list (list-str): files to be watched"""
        self.file_list = set([os.path.abspath(f) for f in file_list])
        self.watch_dirs = set([os.path.dirname(f) for f in self.file_list])
        self.notifier = None

    def _handle(self, event):
        if event.pathname in self.file_list:
            self.handle_event(event)

    def handle_event(self, event):
        """this should be sub-classed """
        raise NotImplementedError

    def loop(self, loop_callback=None):
        """Infinite loop
        @loop_callback: used to stop loop on unittests
        """
        import pyinotify
        handler = self._handle
        class EventHandler(pyinotify.ProcessEvent):
            def process_default(self, event):
                handler(event)

        wm = pyinotify.WatchManager()  # Watch Manager
        mask = pyinotify.IN_CLOSE_WRITE
        ev = EventHandler()
        self.notifier = pyinotify.Notifier(wm, ev)

        for watch_this in self.watch_dirs:
            wm.add_watch(watch_this, mask)

        self.notifier.loop(loop_callback)


def doit_auto(dependency_file, task_list, filter_tasks, loop_callback=None):
    """Re-execute tasks automatically a depedency changes

    @param filter_tasks (list -str): print only tasks from this list
    @loop_callback: used to stop loop on unittests
    """
    selected_tasks = TaskSetup(task_list, filter_tasks).process()
    watch_files = list(itertools.chain(*[s.file_dep for s in selected_tasks]))

    class DoitAutoRun(FileModifyWatcher):
        def handle_event(self, event):
            doit_run(dependency_file, task_list, sys.stdout,
                     filter_tasks, reporter='executed-only')

    fw = DoitAutoRun(watch_files)
    fw.loop(loop_callback)
