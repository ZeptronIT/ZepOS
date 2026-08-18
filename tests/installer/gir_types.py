# SPDX-License-Identifier: GPL-3.0-or-later
"""Read GTK's own type information, and check the GUI's calls against it.

NOT a test module - pytest does not collect this file.
tests/installer/test_gui_widget_types.py is the caller.

WHY THIS EXISTS NEXT TO THE HEADLESS SMOKE TEST
    tests/installer/test_gui_headless.py executes the widget tree, which
    is the stronger check by far - but it only sees lines it reaches. A
    branch that needs a machine with no wireless adapter, an SVG that
    will not load, or an installation that fails is a branch it does not
    execute. This reads every line whether or not anything runs it, and
    it costs no display, no GTK and no subprocess.

    Neither replaces the other and both are cheap. e1e21cd would have
    been caught by either.

WHERE THE TYPES COME FROM
    /usr/share/gir-1.0/*.gir - the XML GObject-Introspection files that
    the typelibs PyGObject reads at runtime are compiled from. Parsing
    the XML rather than importing gi keeps this runnable in the virtual
    environment, which has no PyGObject in it; the argument types are
    the same ones PyGObject marshals against, because they are the same
    source.

WHAT THIS CAN SEE
    A receiver whose type is pinned by something in the file itself - a
    constructor call (`page = Adw.PreferencesPage()`), a parameter
    annotation (`group: Adw.PreferencesGroup`), an attribute assigned
    from a constructor (`self.stack = Gtk.Stack()`), or a method whose
    return type is annotated - and an argument whose type is pinned the
    same way. Given both, the declared parameter type from the GIR
    decides.

WHAT THIS CANNOT SEE, AND THE READER SHOULD NOT ASSUME IT DOES
    * a value whose type nothing in the file states: a widget out of a
      list, a getter's result, a variable rebound in two branches.
      Unknown types are skipped in silence rather than guessed at.
    * keyword arguments to methods; only positional ones are matched
      against the parameter list.
    * anything about what a call MEANS. Adw.PreferencesGroup.add() is
      declared to take a Gtk.Widget, so putting a Gtk.Button in a
      preferences group is not a type error here - and it is not one at
      runtime either. It is a design question no type system answers.
    * GVariant, GValue and other cases where the C type is a container
      whose real requirement is written in prose.
    * a method PyGObject does not export under the name the GIR gives
      it. MEASURED on Adw.AlertDialog.response(): the GIR lists it as an
      ordinary method, the type also has a SIGNAL called "response", and
      the signal wins - dialog.response("yes") is an AttributeError,
      while this file would call it correct. The rule is general (a
      method whose name collides with a signal on the same type), the
      case was found by the execution test, and it is the clearest
      illustration of why both guards exist.

    So: findings from this file are real, and a clean run is not proof.
    The execution test is what proves.
"""
from __future__ import annotations

import ast
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

GIR_NS = "{http://www.gtk.org/introspection/core/1.0}"
GIR_DIR = Path("/usr/share/gir-1.0")

# The namespaces installer/gui/ can name, plus the ones their types
# inherit from. A namespace whose file is missing simply yields no types,
# and every call through it becomes unknown rather than a false finding.
NAMESPACE_FILES = {
    "Gtk": "Gtk-4.0.gir",
    "Adw": "Adw-1.gir",
    "Gdk": "Gdk-4.0.gir",
    "Gio": "Gio-2.0.gir",
    "GObject": "GObject-2.0.gir",
    "GLib": "GLib-2.0.gir",
    "Pango": "Pango-1.0.gir",
    "GdkPixbuf": "GdkPixbuf-2.0.gir",
    "Gsk": "Gsk-4.0.gir",
    "Graphene": "Graphene-1.0.gir",
}


@dataclass(frozen=True)
class Finding:
    """One call this file is prepared to say is wrong."""

    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


@dataclass
class GirType:
    name: str
    parent: str | None
    implements: tuple[str, ...]
    # name -> [(parameter name, parameter type or None)]
    methods: dict[str, list[tuple[str, str | None]]] = field(default_factory=dict)
    # name -> (parameters, return type); constructors and static functions
    statics: dict[str, tuple[list[tuple[str, str | None]], str | None]] = field(
        default_factory=dict)
    constructors: frozenset[str] = frozenset()
    properties: frozenset[str] = frozenset()


class GirIndex:
    """Every class, interface and record in the namespaces above."""

    def __init__(self, gir_dir: Path = GIR_DIR) -> None:
        self.types: dict[str, GirType] = {}
        self.namespaces: set[str] = set()
        for namespace, filename in NAMESPACE_FILES.items():
            path = gir_dir / filename
            if path.is_file():
                self._load(namespace, path)
                self.namespaces.add(namespace)

    @staticmethod
    def _qualify(namespace: str, raw: str | None) -> str | None:
        """GIR writes a name from another namespace as "Gtk.Widget" and
        one from its own as plain "Widget"."""
        if raw is None:
            return None
        return raw if "." in raw else f"{namespace}.{raw}"

    def _parameters(self, namespace: str, node) -> list[tuple[str, str | None]]:
        holder = node.find(GIR_NS + "parameters")
        if holder is None:
            return []
        parameters = []
        for parameter in holder.findall(GIR_NS + "parameter"):
            declared = parameter.find(GIR_NS + "type")
            parameters.append((
                parameter.get("name") or "",
                self._qualify(namespace, declared.get("name"))
                if declared is not None else None,
            ))
        return parameters

    def _return(self, namespace: str, node) -> str | None:
        value = node.find(GIR_NS + "return-value")
        if value is None:
            return None
        declared = value.find(GIR_NS + "type")
        return (self._qualify(namespace, declared.get("name"))
                if declared is not None else None)

    def _load(self, namespace: str, path: Path) -> None:
        root = ET.parse(path).getroot()
        for kind in ("class", "interface", "record"):
            for node in root.iter(GIR_NS + kind):
                name = node.get("name")
                if not name:
                    continue
                qualified = f"{namespace}.{name}"
                inherited = tuple(
                    self._qualify(namespace, related.get("name")) or ""
                    for tag in ("implements", "prerequisite")
                    for related in node.findall(GIR_NS + tag)
                )
                entry = GirType(
                    qualified, self._qualify(namespace, node.get("parent")), inherited)
                for method in node.findall(GIR_NS + "method"):
                    entry.methods[method.get("name")] = self._parameters(
                        namespace, method)
                for method in node.findall(GIR_NS + "virtual-method"):
                    entry.methods.setdefault(
                        method.get("name"), self._parameters(namespace, method))
                constructors = set()
                for method in node.findall(GIR_NS + "constructor"):
                    # The OWNING class, not the declared return type. Most
                    # Gtk constructors are declared to return Gtk.Widget
                    # (Gtk.Picture.new_for_filename among them), while
                    # PyGObject hands back a wrapper for the real GType.
                    # Trusting the declaration would lose the subclass and
                    # then report every Gtk.Picture method as unknown.
                    entry.statics[method.get("name")] = (
                        self._parameters(namespace, method), qualified)
                    constructors.add(method.get("name"))
                for function in node.findall(GIR_NS + "function"):
                    entry.statics[function.get("name")] = (
                        self._parameters(namespace, function),
                        self._return(namespace, function))
                entry.constructors = frozenset(constructors)
                entry.properties = frozenset(
                    (property_node.get("name") or "").replace("-", "_")
                    for property_node in node.findall(GIR_NS + "property"))
                self.types[qualified] = entry

    def knows(self, name: str | None) -> bool:
        return name is not None and name in self.types

    def ancestors(self, name: str) -> list[str]:
        """name, its parents, and every interface any of them implements."""
        seen: list[str] = []
        pending = [name]
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.append(current)
            entry = self.types.get(current)
            if entry is None:
                continue
            if entry.parent:
                pending.append(entry.parent)
            pending.extend(interface for interface in entry.implements if interface)
        return seen

    def find_method(self, type_name: str, method: str):
        for ancestor in self.ancestors(type_name):
            entry = self.types.get(ancestor)
            if entry is not None and method in entry.methods:
                return ancestor, entry.methods[method]
        return None

    def has_property(self, type_name: str, name: str) -> bool:
        return any(
            name in entry.properties
            for entry in (self.types.get(a) for a in self.ancestors(type_name))
            if entry is not None
        )

    def accepts(self, given: str, declared: str) -> bool:
        return declared in self.ancestors(given)


class ModuleCheck(ast.NodeVisitor):
    """One python file, checked against a GirIndex."""

    def __init__(self, path: str, source: str, index: GirIndex) -> None:
        self.path = path
        self.index = index
        self.tree = ast.parse(source, path)
        self.gi_namespaces: set[str] = set()
        self.class_bases: dict[str, str] = {}
        self.class_attributes: dict[str, dict[str, str | None]] = {}
        self.class_methods: dict[str, dict[str, str | None]] = {}
        self.findings: list[Finding] = []

    # --- what the file imported and declared ----------------------------

    def _collect_imports(self) -> None:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and node.module == "gi.repository":
                for alias in node.names:
                    name = alias.asname or alias.name
                    if alias.name in self.index.namespaces:
                        self.gi_namespaces.add(name)

    def _gi_type(self, node) -> str | None:
        """`Gtk.Label` as an expression -> "Gtk.Label", if GIR has it."""
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id in self.gi_namespaces):
            qualified = f"{node.value.id}.{node.attr}"
            if self.index.knows(qualified):
                return qualified
        return None

    def _annotation_type(self, annotation) -> str | None:
        if annotation is None:
            return None
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            try:
                annotation = ast.parse(annotation.value, mode="eval").body
            except SyntaxError:
                return None
        if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
            # "Gtk.Widget | None" - the widget half is the informative one.
            return (self._annotation_type(annotation.left)
                    or self._annotation_type(annotation.right))
        return self._gi_type(annotation)

    def _collect_classes(self) -> None:
        for node in self.tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                found = self._gi_type(base)
                if found:
                    self.class_bases[node.name] = found
            self.class_methods[node.name] = {
                child.name: self._annotation_type(child.returns)
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
        # A second pass, because an attribute's initialiser can mention a
        # method whose return annotation the pass above just recorded.
        for node in self.tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            attributes: dict[str, str | None] = {}
            for child in ast.walk(node):
                if isinstance(child, ast.AnnAssign):
                    target = child.target
                    if (isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"):
                        attributes[target.attr] = self._annotation_type(
                            child.annotation)
                elif isinstance(child, ast.Assign):
                    for target in child.targets:
                        if not (isinstance(target, ast.Attribute)
                                and isinstance(target.value, ast.Name)
                                and target.value.id == "self"):
                            continue
                        found = self._expression_type(child.value, {}, node.name)
                        if target.attr in attributes and attributes[target.attr] != found:
                            # Assigned two different things in two places.
                            # Nothing here can say which one a given call
                            # site sees, so it says nothing.
                            attributes[target.attr] = None
                        else:
                            attributes[target.attr] = found
            self.class_attributes[node.name] = attributes

    # --- the type of one expression, or None ------------------------------

    def _expression_type(self, node, scope, class_name) -> str | None:
        if isinstance(node, ast.Name):
            return scope.get(node.id)
        if isinstance(node, ast.Attribute):
            if (isinstance(node.value, ast.Name) and node.value.id == "self"
                    and class_name):
                return self.class_attributes.get(class_name, {}).get(node.attr)
            return self._gi_type(node)
        if not isinstance(node, ast.Call):
            return None
        constructed = self._gi_type(node.func)
        if constructed:
            return constructed
        if not isinstance(node.func, ast.Attribute):
            return None
        owner = self._gi_type(node.func.value)
        if owner:
            entry = self.index.types.get(owner)
            if entry is not None and node.func.attr in entry.statics:
                return entry.statics[node.func.attr][1]
            return None
        if (isinstance(node.func.value, ast.Name) and node.func.value.id == "self"
                and class_name):
            return self.class_methods.get(class_name, {}).get(node.func.attr)
        return None

    # --- the checks -------------------------------------------------------

    def run(self) -> list[Finding]:
        self._collect_imports()
        self._collect_classes()
        for node in self.tree.body:
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self._check_function(child, node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._check_function(node, None)
        return self.findings

    @staticmethod
    def _takes_instance(function) -> bool:
        """Ob das erste Argument dieser Funktion die Instanz IST.

        Bei einer gewoehnlichen Methode ja - sie heisst `self` und traegt
        den Typ der Klasse. Bei `@staticmethod` nein: dort ist das erste
        Argument ein ganz gewoehnliches, und bei `@classmethod` ist es
        die Klasse und keine Instanz.

        GEMESSEN am 12.08.2026 an installer/gui/app.py: `_replace_tail`
        ist eine `@staticmethod` mit der Signatur `(buffer, rendered)`.
        Ohne diese Unterscheidung bekam `buffer` den Typ der umgebenden
        Klasse - Adw.ApplicationWindow - und dieser Waechter meldete eine
        Klasse ohne `get_end_iter()`, `get_start_iter()`, `delete()` und
        `insert()`: ELF Funde in EINER Methode, alle falsch, und jeder
        von ihnen ueber eine Zeile, die auf dem Medium taeglich laeuft.

        Ein Waechter, der Falsches meldet, ist schlimmer als keiner: er
        kostet bei jedem Lauf die Entscheidung, ob man ihm diesmal
        glaubt.
        """
        for decorator in function.decorator_list:
            name = (decorator.id if isinstance(decorator, ast.Name)
                    else decorator.attr if isinstance(decorator, ast.Attribute)
                    else None)
            if name in ("staticmethod", "classmethod"):
                return False
        return True

    def _check_function(self, function, class_name: str | None) -> None:
        scope: dict[str, str | None] = {}
        for argument in list(function.args.args) + list(function.args.kwonlyargs):
            annotated = self._annotation_type(argument.annotation)
            if annotated:
                scope[argument.arg] = annotated
        if (class_name in self.class_bases and function.args.args
                and self._takes_instance(function)):
            scope[function.args.args[0].arg] = self.class_bases[class_name]

        # Names first, calls afterwards: a nested callback defined above
        # its own trigger still sees the enclosing function's variables,
        # and ast.walk visits both in one flat pass.
        for node in ast.walk(function):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        found = self._expression_type(node.value, scope, class_name)
                        if found:
                            scope[target.id] = found
        for node in ast.walk(function):
            if isinstance(node, ast.Call):
                self._check_call(node, scope, class_name)

    def _check_call(self, node: ast.Call, scope, class_name) -> None:
        constructed = self._gi_type(node.func)
        if constructed:
            self._check_construction(node, constructed)
            return
        if not isinstance(node.func, ast.Attribute):
            return
        method = node.func.attr
        receiver = node.func.value
        if isinstance(receiver, ast.Name) and receiver.id == "self" and class_name:
            if method in self.class_methods.get(class_name, {}):
                return
            if method in self.class_attributes.get(class_name, {}):
                # An attribute holding a callable, not a method of the
                # GObject base - e.g. an injected dependency.
                return
            receiver_type = self.class_bases.get(class_name)
        else:
            receiver_type = self._expression_type(receiver, scope, class_name)
        if not self.index.knows(receiver_type):
            return

        found = self.index.find_method(receiver_type, method)
        if found is None:
            entry = self.index.types.get(receiver_type)
            if entry is not None and method in entry.statics:
                return
            if self.index.has_property(receiver_type, method):
                return
            self.findings.append(Finding(
                self.path, node.lineno,
                f"{receiver_type} has no method {method}() - GIR knows this "
                "type and not that name, so the call raises AttributeError "
                "the first time it is reached"))
            return

        owner, parameters = found
        for position, argument in enumerate(node.args):
            if position >= len(parameters):
                break
            declared_name, declared_type = parameters[position]
            if not self.index.knows(declared_type):
                continue
            if (isinstance(argument, ast.Constant)
                    and argument.value is not None
                    and not isinstance(argument.value, bytes)):
                # A literal where an object is declared. Almost always
                # two arguments the wrong way round -
                # Gtk.Stack.add_named(name, child) reads perfectly well
                # and is backwards. None is left alone: a nullable
                # parameter is normal and GIR's own nullable flag is not
                # reliable enough to argue with.
                self.findings.append(Finding(
                    self.path, node.lineno,
                    f"{owner}.{method}() takes {declared_type} as "
                    f"'{declared_name}', and is given the literal "
                    f"{argument.value!r} - check the argument order"))
                continue
            given = self._expression_type(argument, scope, class_name)
            if not self.index.knows(given):
                continue
            if not self.index.accepts(given, declared_type):
                self.findings.append(Finding(
                    self.path, node.lineno,
                    f"{owner}.{method}() takes {declared_type} as "
                    f"'{declared_name}', and is given {given} - PyGObject "
                    "raises TypeError here, at the moment this line runs"))

    def _check_construction(self, node: ast.Call, type_name: str) -> None:
        """Keyword arguments to a widget constructor are property names.

        PyGObject turns Adw.EntryRow(title=...) into g_object_new with
        that construct property. A name the type does not have is a
        TypeError from the constructor, and it is not visible anywhere
        until the line runs.
        """
        for keyword in node.keywords:
            if keyword.arg is None:
                continue
            if not self.index.has_property(type_name, keyword.arg):
                self.findings.append(Finding(
                    self.path, node.lineno,
                    f"{type_name} has no property '{keyword.arg}' - "
                    "PyGObject builds this widget with g_object_new and "
                    "raises TypeError on an unknown construct property"))


def check_tree(paths, index: GirIndex | None = None) -> list[Finding]:
    """Every finding across a set of python files, in file order."""
    index = index or GirIndex()
    findings: list[Finding] = []
    for path in sorted(paths):
        path = Path(path)
        findings.extend(
            ModuleCheck(str(path), path.read_text(encoding="utf-8"), index).run())
    return findings
