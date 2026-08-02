"""示例数据生成脚本。

用法：
    python seed_demo.py

创建 1 个"新需求"示例项目，应用模板 A，填充示例日期/进度/负责人，
便于在 Swagger UI 里直接看到完整的数据形态。

幂等：重复运行会先删除同名项目再重建。
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select  # noqa: E402

from app import models  # noqa: E402,F401
from app.database import SessionLocal  # noqa: E402
from app.models import Phase, Project, Resource, Template  # noqa: E402
from app.services import apply_template  # noqa: E402

_DEMO_PROJECT_CODE = "DEMO-01"


def _seed_people(db) -> dict[str, Resource]:
    """创建示例人员，返回 {name: Resource}。"""
    people = ["曹俊杰", "李明", "王工", "张测试", "陈管理"]
    result: dict[str, Resource] = {}
    for name in people:
        r = db.scalars(select(Resource).where(Resource.name == name)).first()
        if r is None:
            r = Resource(name=name)
            db.add(r)
            db.flush()
        result[name] = r
    return result


def main() -> None:
    print("=" * 50)
    print("生成示例数据")
    print("=" * 50)
    db = SessionLocal()
    try:
        # 人员
        people = _seed_people(db)
        print(f"✓ 人员就绪：{list(people.keys())}")

        # 模板 A
        tpl = db.scalars(select(Template).where(Template.name == "招标/新品研发标准流程")).first()
        if tpl is None:
            print("✗ 找不到模板 A，请先运行 init_db.py")
            return

        # 幂等删除旧 demo 项目
        old = db.scalars(select(Project).where(Project.code == _DEMO_PROJECT_CODE)).first()
        if old:
            db.delete(old)
            db.flush()

        project = Project(
            code=_DEMO_PROJECT_CODE,
            category="新需求",
            name="示例：工行自提穿墙主柜 TCM10-012",
            owner="陈管理",
            market="国内",
            status="进行中",
            priority="高",
            plan_start=date.today() - timedelta(days=20),
            plan_end=date.today() + timedelta(days=40),
            remark="seed_demo.py 生成的示例项目，可随时删除",
        )
        db.add(project)
        db.flush()

        # 应用模板 A → 生成阶段 + 依赖
        created = apply_template(db, project.id, tpl.id)
        db.flush()
        print(f"✓ 项目 {project.code} 创建，应用模板 A 生成 {len(created)} 个阶段")

        # 给前 4 个阶段填示例状态/进度/负责人
        role_map = {
            "P1": people["陈管理"],
            "P2": people["陈管理"],
            "P3": people["王工"],
            "P4": people["曹俊杰"],
            "P5": people["李明"],
            "P6": people["李明"],
            "P7": people["张测试"],
            "P8": people["陈管理"],
        }
        for ph in created:
            if ph.phase_type in ("P1", "P2", "P3"):
                ph.status = "已完成"
                ph.progress = 100
                ph.actual_start = ph.plan_start
                ph.actual_end = ph.plan_end
            elif ph.phase_type == "P4":
                ph.status = "进行中"
                ph.progress = 60
                ph.actual_start = ph.plan_start
            res = role_map.get(ph.phase_type)
            if res:
                ph.assignees = [res]
        db.commit()

        print(f"\n✅ 示例项目完成。访问 http://localhost:8000/api/projects/{project.id}/gantt 查看甘特图数据")
        print("   Swagger UI: http://localhost:8000/docs")
    finally:
        db.close()


if __name__ == "__main__":
    main()
