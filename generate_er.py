from app import app, db
from sqlalchemy_schemadisplay import create_schema_graph


def generate_er():
    with app.app_context():
        # Create the graph
        graph = create_schema_graph(
            metadata=db.metadata,
            show_datatypes=False,  # The image would get nasty big if we'd show the datatypes
            show_indexes=False,  # ditto for indexes
            rankdir="LR",  # From left to right (instead of top to bottom)
            concentrate=False,  # Don't try to join the relation lines together
        )

        # Write to PNG
        try:
            graph.write_png("er_diagram.png")
            print("ER Diagram generated at 'er_diagram.png'")
        except Exception as e:
            print(f"Error generating PNG: {e}")
            print(
                "Make sure graphviz is installed on the system (apt install graphviz)"
            )

            # Fallback to DOT
            graph.write_dot("er_diagram.dot")
            print("Generated 'er_diagram.dot'. You can render it using graphviz.")


if __name__ == "__main__":
    try:
        generate_er()
    except ImportError:
        print(
            "Please install sqlalchemy_schemadisplay: pip install sqlalchemy_schemadisplay pydot"
        )
