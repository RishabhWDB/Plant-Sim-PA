using UnityEngine;

public class FarmGrid : MonoBehaviour
{
    [Header("Grid Settings")]
    public GameObject plantPrefab;
    public int rows = 5;
    public int columns = 5;
    public float spacing = 3f;

    [Header("Variation")]
    public float individualOffsetRange = 0.05f;

    private Plant[] allPlants;

    void Start()
    {
        SpawnGrid();
    }

    void SpawnGrid()
    {
        allPlants = new Plant[rows * columns];

        float totalWidth  = (columns - 1) * spacing;
        float totalLength = (rows - 1)    * spacing;

        // Center the grid at this object's position
        Vector3 origin = transform.position - new Vector3(
            totalWidth  / 2f,
            0f,
            totalLength / 2f
        );

        int index = 0;
        for (int r = 0; r < rows; r++)
        {
            for (int c = 0; c < columns; c++)
            {
                Vector3 spawnPos = origin + new Vector3(
                    c * spacing,
                    0f,
                    r * spacing
                );

                GameObject obj = Instantiate(plantPrefab, spawnPos, Quaternion.identity);
                obj.name = $"Plant_{r}_{c}";
                obj.transform.parent = transform;

                Plant plant = obj.GetComponent<Plant>();
                if (plant == null)
                    plant = obj.AddComponent<Plant>();

                // Assign a unique random offset so plants grow slightly differently
                plant.individualOffset = Random.Range(
                    -individualOffsetRange,
                     individualOffsetRange
                );

                allPlants[index] = plant;
                index++;
            }
        }

        Debug.Log($"FarmGrid: Spawned {allPlants.Length} plants ({rows}x{columns})");
    }

    public Plant[] GetAllPlants()
    {
        return allPlants;
    }
}