/**
 * Nova Debug - Copy này vào browser console (F12) để debug
 * 
 * 1. localStorage.getItem("userId") - kiểm tra teacher_id
 * 2. localStorage.getItem("currentClassId") - kiểm tra class_id đã lưu
 * 3. window.location.pathname - kiểm tra URL
 */

console.log("=== NOVA DEBUG ===");
console.log("User ID:", localStorage.getItem("userId"));
console.log("Current Class ID:", localStorage.getItem("currentClassId"));
console.log("Current URL:", window.location.pathname);

// Simulate NovaTeacherAgent logic
const pathname = window.location.pathname;
const pathParts = pathname?.split("/").filter(Boolean) || [];
console.log("Path parts:", pathParts);

let classId = null;
if (pathParts.length > 2) {
  const potentialId = pathParts[pathParts.length - 1];
  if (!isNaN(Number(potentialId))) {
    classId = parseInt(potentialId);
    console.log("✅ Found class_id in URL:", classId);
  }
}

if (!classId) {
  const storedClassId = localStorage.getItem("currentClassId");
  if (storedClassId) {
    classId = parseInt(storedClassId);
    console.log("✅ Found class_id in localStorage:", classId);
  }
}

console.log("Final class_id:", classId);

// Test API
console.log("\n=== TESTING API ===");
const teacherId = localStorage.getItem("userId");
if (teacherId && classId) {
  fetch("/api/teacher/nova-interactive", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      teacher_id: parseInt(teacherId),
      class_id: classId,
      message: "test"
    })
  })
  .then(r => r.json())
  .then(data => console.log("✅ API Response:", data.reply?.substring(0, 100)))
  .catch(e => console.error("❌ API Error:", e));
} else {
  console.error("❌ Missing teacher_id or class_id");
}
