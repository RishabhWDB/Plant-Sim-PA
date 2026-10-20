using System;
using UnityEngine;

/// <summary>
/// Evaluates the trained growth-score surrogate exported by train_model.py (growth_model.json):
/// a histogram gradient-boosting ensemble followed by isotonic calibration.
/// Inputs: pH, soil moisture (%), sunlight (h/day), temperature (C), humidity (%), growth stage (0-6).
/// The traversal mirrors reference_eval() in train_model.py, which matches scikit-learn exactly.
/// </summary>
public class GrowthModel
{
    [Serializable]
    public class Tree
    {
        public int[] feature;
        public double[] threshold;
        public int[] left;
        public int[] right;
        public int[] leaf;
        public double[] value;
    }

    [Serializable]
    public class Data
    {
        public int version;
        public string[] features;
        public double baseline;
        public Tree[] trees;
        public double[] isotonic_x;
        public double[] isotonic_y;
        public double conformal_q90;
    }

    private Data data;
    private readonly double[] x = new double[6];

    /// <summary>Half-width of the 90% split-conformal interval around a prediction.</summary>
    public float ConformalQ90 => (float)data.conformal_q90;
    public int TreeCount => data.trees.Length;

    public static GrowthModel Load(string json)
    {
        var model = new GrowthModel { data = JsonUtility.FromJson<Data>(json) };
        if (model.data == null || model.data.trees == null || model.data.trees.Length == 0)
            throw new Exception("growth_model.json could not be parsed or contains no trees.");
        if (model.data.isotonic_x == null || model.data.isotonic_x.Length < 2)
            throw new Exception("growth_model.json has no isotonic calibration.");
        return model;
    }

    public float Predict(float pH, float soilMoisture, float sunlight, float temperature, float humidity, int stage)
    {
        x[0] = pH; x[1] = soilMoisture; x[2] = sunlight; x[3] = temperature; x[4] = humidity; x[5] = stage;

        double total = data.baseline;
        Tree[] trees = data.trees;
        for (int t = 0; t < trees.Length; t++)
        {
            Tree tree = trees[t];
            int n = 0;
            while (tree.leaf[n] == 0)
                n = x[tree.feature[n]] <= tree.threshold[n] ? tree.left[n] : tree.right[n];
            total += tree.value[n];
        }

        double raw = Math.Min(1.0, Math.Max(0.0, total));
        return (float)Math.Min(1.0, Math.Max(0.0, Calibrate(raw)));
    }

    private double Calibrate(double r)
    {
        double[] xs = data.isotonic_x, ys = data.isotonic_y;
        int last = xs.Length - 1;
        if (r <= xs[0]) return ys[0];
        if (r >= xs[last]) return ys[last];

        int lo = 0, hi = last;                       // binary search: xs[lo] <= r < xs[hi]
        while (hi - lo > 1)
        {
            int mid = (lo + hi) / 2;
            if (xs[mid] <= r) lo = mid; else hi = mid;
        }
        return ys[lo] + (ys[hi] - ys[lo]) * (r - xs[lo]) / (xs[hi] - xs[lo]);
    }
}
